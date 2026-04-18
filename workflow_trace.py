"""
Trace-enabled workflow entrypoint.

This mirrors the Phase 3 main workflow while recording per-node IO snapshots,
timing, and changed top-level state fields.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable
import copy
import json
import os
import time

from langgraph.errors import GraphInterrupt
from langgraph.graph import StateGraph
from langsmith import traceable

from agents.analysis_agent import AnalysisAgent
from agents.ambiguity_router import AmbiguityRouter
from agents.architecture_feedback_apply_agent import ArchitectureFeedbackApplyAgent
from agents.architecture_planner import ArchitecturePlanner
from agents.architecture_review_agent import ArchitectureReviewAgent
from agents.clarification_apply_agent import ClarificationApplyAgent
from agents.clarification_review_agent import ClarificationReviewAgent
from agents.coding_agent import CodingAgent
from agents.global_assembler import GlobalAssembler
from agents.repair_agent import RepairAgent
from agents.repair_router import RepairRouter
from agents.subsystem_planner import SubsystemPlanner
from agents.verifier_agent import VerifierAgent
from workflow import (
    PHASE4_RECURSION_LIMIT,
    WorkflowState,
    build_initial_state,
    populate_phase4_workflow,
)
from utils.phase6_diagnostics import derive_failure_bucket, ordered_subsystem_ids
from utils.review_index import save_review_artifacts
from utils.trace_index import generate_attempt_id, register_trace_attempt
from utils.workflow_runtime import build_runtime_invoke_config, compile_state_graph

try:
    from agents.retrieval_agent import RetrievalAgent
except ModuleNotFoundError:
    RetrievalAgent = None

os.environ["LANGCHAIN_TRACING_V2"] = "false"
TRACE_OUTPUT_ROOT = "outputs"


def _make_serializable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {key: _make_serializable(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_make_serializable(item) for item in obj]
    if isinstance(obj, tuple):
        return [_make_serializable(item) for item in obj]
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    return str(obj)


def _truncate_for_display(value: Any, max_len: int = 3000) -> Any:
    if isinstance(value, dict):
        return {key: _truncate_for_display(item, max_len) for key, item in value.items()}
    if isinstance(value, list):
        return [_truncate_for_display(item, max_len) for item in value]
    if isinstance(value, str) and len(value) > max_len:
        return value[:max_len] + f"... (共{len(value)}字符)"
    return value


def _get_changed_fields(before_state: dict, after_state: dict) -> list[str]:
    changed_fields = []
    for key, value in after_state.items():
        if key not in before_state or before_state.get(key) != value:
            changed_fields.append(key)
    return changed_fields


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return default


def _count_subsystem_modes(subsystem_plan_map: dict[str, Any]) -> dict[str, int]:
    counts = {
        "reuse_template_subsystem_count": 0,
        "atomic_assembly_subsystem_count": 0,
    }
    for plan in (subsystem_plan_map or {}).values():
        mode = str((plan or {}).get("implementation_mode", "")).strip()
        if mode == "reuse_template":
            counts["reuse_template_subsystem_count"] += 1
        elif mode == "atomic_assembly":
            counts["atomic_assembly_subsystem_count"] += 1
    return counts


def _normalize_retry_counts_by_scope(retry_counts_by_scope: dict[str, Any] | None) -> dict[str, int]:
    normalized = {
        "planning": 0,
        "assembly": 0,
        "compile": 0,
    }
    if retry_counts_by_scope is None:
        return normalized
    for scope in normalized:
        normalized[scope] = _to_int(retry_counts_by_scope.get(scope, 0))
    return normalized


def _ordered_unique_scopes(scopes: list[Any]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for scope in scopes:
        normalized = str(scope or "").strip()
        if not normalized or normalized == "none" or normalized in seen:
            continue
        ordered.append(normalized)
        seen.add(normalized)
    return ordered


def _planning_unresolved_by_type(unresolved_items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in unresolved_items:
        if not isinstance(item, dict):
            continue
        if str(item.get("scope", "")).strip() != "planning":
            continue
        issue_type = str(item.get("type", "")).strip() or "unknown"
        counts[issue_type] = counts.get(issue_type, 0) + 1
    return dict(sorted(counts.items()))


def _normalize_signal_key(value: Any) -> str:
    return str(value or "").strip()


def _collect_ambiguous_signal_keys(final_state: dict[str, Any], unresolved_items: list[dict[str, Any]]) -> set[str]:
    ambiguous_keys: set[str] = set()

    for registry_key in ("architecture_plan", "decomposition_result"):
        registry = ((final_state or {}).get(registry_key, {}) or {}).get("shared_signal_registry", []) or []
        for entry in registry:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("resolution_status", "")).strip() != "ambiguous":
                continue
            signal_key = (
                _normalize_signal_key(entry.get("canonical_signal_key"))
                or _normalize_signal_key(entry.get("signal_key"))
                or _normalize_signal_key(entry.get("signal_name"))
            )
            if signal_key:
                ambiguous_keys.add(signal_key)

    for item in unresolved_items:
        if not isinstance(item, dict):
            continue
        if str(item.get("type", "")).strip() != "ambiguous_shared_signal":
            continue
        signal_key = (
            _normalize_signal_key(item.get("canonical_signal_key"))
            or _normalize_signal_key(item.get("signal_key"))
            or _normalize_signal_key(item.get("signal_name"))
        )
        if signal_key:
            ambiguous_keys.add(signal_key)

    verification_issues = ((final_state or {}).get("verification_report", {}) or {}).get("issues", []) or []
    for issue in verification_issues:
        if not isinstance(issue, dict):
            continue
        repair_payload = issue.get("repair_payload", {}) if isinstance(issue.get("repair_payload"), dict) else {}
        if (
            str(issue.get("rule_id", "")).strip() != "ir.unresolved.ambiguous_shared_signal"
            and str(repair_payload.get("resolution_status", "")).strip() != "ambiguous"
        ):
            continue
        signal_key = (
            _normalize_signal_key(repair_payload.get("canonical_signal_key"))
            or _normalize_signal_key(issue.get("target_id"))
        )
        if signal_key:
            ambiguous_keys.add(signal_key)

    return ambiguous_keys


def _repair_reject_category(route_decision: dict[str, Any]) -> str:
    decision = str((route_decision or {}).get("decision", "")).strip()
    if decision != "reject":
        return ""

    reason = str((route_decision or {}).get("reason", "")).strip()
    reject_categories = {
        "ambiguous_shared_signal_unresolved": "ambiguous_shared_signal",
        "retry_budget_exhausted": "budget_exhausted",
        "unsupported_repair_issue": "unsupported_repair_issue",
        "unsupported_repair_scope": "unsupported_repair_scope",
        "no_repairable_issue": "no_repairable_issue",
        "repair_patch_failed": "repair_patch_failed",
    }
    return reject_categories.get(reason, reason)


def _build_trace_summary(
    user_query: str,
    node_io_records: list[dict],
    final_state: dict,
    total_elapsed_seconds: float,
    *,
    thread_id: str | None = None,
    attempt_id: str | None = None,
    approval_record_json: str = "",
) -> dict:
    retrieval_metadata = ((final_state or {}).get("retrieval_bundle", {}) or {}).get("metadata", {}) or {}
    subsystem_plan_map = (final_state or {}).get("subsystem_plan_map", {}) or {}
    architecture_plan = (final_state or {}).get("architecture_plan", {}) or {}
    assembled_graph_ir = (final_state or {}).get("assembled_graph_ir", {}) or {}
    compiled_artifact = (final_state or {}).get("compiled_artifact", {}) or {}
    verification_report = (final_state or {}).get("verification_report", {}) or {}
    repair_history = list((final_state or {}).get("repair_history", []) or [])
    route_decision = (final_state or {}).get("route_decision", {}) or {}
    retry_counts_by_scope = _normalize_retry_counts_by_scope((final_state or {}).get("retry_counts_by_scope"))
    review_request = (final_state or {}).get("review_request", {}) or {}
    review_response = (final_state or {}).get("review_response", {}) or {}
    review_history = list((final_state or {}).get("review_history", []) or [])
    hitl_stage = str((final_state or {}).get("hitl_stage", "") or "none").strip() or "none"
    review_enabled = bool((final_state or {}).get("review_enabled", False))
    review_required = bool((final_state or {}).get("review_required", False))
    review_status = str((final_state or {}).get("review_status", "") or "none").strip() or "none"
    review_id = str((final_state or {}).get("review_id", "") or "").strip()
    interrupted_record = next(
        (record for record in reversed(node_io_records) if record.get("status") == "interrupted"),
        {},
    )
    interrupted = bool(interrupted_record) or bool((final_state or {}).get("__interrupt__"))
    request_stage = str(review_request.get("stage", "") or "").strip()
    if interrupted:
        workflow_status = "interrupted"
        if hitl_stage == "none" and request_stage:
            hitl_stage = request_stage
        if review_status in {"none", "pending"} and review_required:
            review_status = "interrupted"

    unresolved_items = list(assembled_graph_ir.get("unresolved_items", []) or [])
    unresolved_error_count = sum(
        1 for item in unresolved_items if str((item or {}).get("severity", "")).strip().lower() == "error"
    )
    unresolved_warning_count = sum(
        1 for item in unresolved_items if str((item or {}).get("severity", "")).strip().lower() == "warning"
    )
    unresolved_item_types = sorted(
        {
            str((item or {}).get("type", "")).strip()
            for item in unresolved_items
            if str((item or {}).get("type", "")).strip()
        }
    )
    planning_unresolved_by_type = _planning_unresolved_by_type(unresolved_items)
    ambiguous_signal_count = len(_collect_ambiguous_signal_keys(final_state, unresolved_items))

    last_successful_node = next(
        (record.get("node_name", "") for record in reversed(node_io_records) if record.get("status") == "success"),
        "",
    )
    failed_record = next(
        (record for record in reversed(node_io_records) if record.get("status") == "error"),
        {},
    )
    failed_output = failed_record.get("output", {}) if isinstance(failed_record, dict) else {}

    verification_status = str(verification_report.get("status", "")).strip()
    if interrupted:
        workflow_status = "interrupted"
    elif failed_record:
        workflow_status = "failed"
    elif verification_status:
        workflow_status = verification_status
    else:
        workflow_status = "completed"

    verification_error_count = len(verification_report.get("issues", []) or [])
    verification_warning_count = len(verification_report.get("warnings", []) or [])
    verification_metrics = verification_report.get("metrics", {}) or {}
    compile_report = compiled_artifact.get("compile_report", {}) or {}
    subsystem_mode_counts = _count_subsystem_modes(subsystem_plan_map)
    subsystem_ids = ordered_subsystem_ids(architecture_plan, subsystem_plan_map)
    last_repair_entry = repair_history[-1] if repair_history else {}
    repair_scopes_seen = _ordered_unique_scopes([
        entry.get("scope", "")
        for entry in repair_history
    ])
    if not repair_scopes_seen:
        repair_scopes_seen = _ordered_unique_scopes([route_decision.get("repair_scope", "")])
    final_route_decision = str(route_decision.get("decision", "")).strip()
    retry_exhausted = bool(route_decision.get("retry_exhausted", False))
    last_repair_issue_ids = list(last_repair_entry.get("issue_ids", []) or route_decision.get("issue_ids", []) or [])
    last_repair_actions = list(last_repair_entry.get("actions", []) or [])
    reject_reason = str(route_decision.get("reason", "")).strip() if final_route_decision == "reject" else ""
    repair_reject_category = _repair_reject_category(route_decision)
    top_atomic_module_types = list(retrieval_metadata.get("top_atomic_module_types", []) or [])
    top_atomic_scores = list(retrieval_metadata.get("top_atomic_scores", []) or [])
    top_subflow_template_ids = list(retrieval_metadata.get("top_subflow_template_ids", []) or [])
    top_subflow_scores = list(retrieval_metadata.get("top_subflow_scores", []) or [])
    top_system_pattern_ids = list(retrieval_metadata.get("top_system_pattern_ids", []) or [])
    top_system_pattern_scores = list(retrieval_metadata.get("top_system_pattern_scores", []) or [])
    query_variants = list(retrieval_metadata.get("query_variants", []) or [])
    llm_queries = list(retrieval_metadata.get("llm_queries", []) or [])
    try:
        analysis_confidence = float(retrieval_metadata.get("analysis_confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        analysis_confidence = 0.0
    failure_bucket = derive_failure_bucket(
        verification_report=verification_report,
        route_decision=route_decision,
        repair_history=repair_history,
        unresolved_item_types=unresolved_item_types,
        repair_reject_category=repair_reject_category,
        workflow_status=workflow_status,
        error_type=str((failed_output or {}).get("error_type", "")).strip(),
        error_message=str((failed_output or {}).get("error_message", "")).strip(),
    )

    acceptance_summary = (
        f"status={verification_status or workflow_status}; "
        f"scope={verification_report.get('repair_scope', 'n/a')}; "
        f"errors={verification_error_count}; warnings={verification_warning_count}; "
        f"unresolved={len(unresolved_items)}; "
        f"reuse_template={subsystem_mode_counts['reuse_template_subsystem_count']}; "
        f"atomic_assembly={subsystem_mode_counts['atomic_assembly_subsystem_count']}"
    )

    return {
        "execution_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user_query": user_query,
        "thread_id": str(thread_id or "").strip(),
        "attempt_id": str(attempt_id or "").strip(),
        "total_elapsed_seconds": round(total_elapsed_seconds, 2),
        "node_count": len(node_io_records),
        "workflow_status": workflow_status,
        "failed_node": str(failed_record.get("node_name", "")).strip(),
        "error_type": str((failed_output or {}).get("error_type", "")).strip(),
        "error_message": str((failed_output or {}).get("error_message", "")).strip(),
        "last_successful_node": str(last_successful_node).strip(),
        "selected_case_pattern_id": str(retrieval_metadata.get("selected_case_pattern_id", "")).strip(),
        "retrieved_atomic_count": _to_int(retrieval_metadata.get("retrieved_atomic_count", 0)),
        "retrieved_subflow_count": _to_int(retrieval_metadata.get("retrieved_subflow_count", 0)),
        "retrieved_pattern_count": _to_int(retrieval_metadata.get("retrieved_pattern_count", 0)),
        "top_atomic_module_types": top_atomic_module_types,
        "top_atomic_scores": top_atomic_scores,
        "top_subflow_template_ids": top_subflow_template_ids,
        "top_subflow_scores": top_subflow_scores,
        "top_system_pattern_ids": top_system_pattern_ids,
        "top_system_pattern_scores": top_system_pattern_scores,
        "query_variants_count": len(query_variants),
        "llm_queries_count": len(llm_queries),
        "rewrite_used": bool(retrieval_metadata.get("rewrite_used", False)),
        "analysis_used": bool(retrieval_metadata.get("analysis_used", False)),
        "analysis_confidence": analysis_confidence,
        "reuse_template_subsystem_count": subsystem_mode_counts["reuse_template_subsystem_count"],
        "atomic_assembly_subsystem_count": subsystem_mode_counts["atomic_assembly_subsystem_count"],
        "subsystem_ids": subsystem_ids,
        "unresolved_item_count": len(unresolved_items),
        "unresolved_error_count": unresolved_error_count,
        "unresolved_warning_count": unresolved_warning_count,
        "unresolved_item_types": unresolved_item_types,
        "planning_unresolved_by_type": planning_unresolved_by_type,
        "ambiguous_signal_count": ambiguous_signal_count,
        "verification_status": verification_status,
        "verification_repair_scope": str(verification_report.get("repair_scope", "")).strip(),
        "verification_issue_summary": str(verification_report.get("issue_summary", "")).strip(),
        "verification_error_count": verification_error_count,
        "verification_warning_count": verification_warning_count,
        "verification_metrics": {
            "missing_required_inputs": _to_int(verification_metrics.get("missing_required_inputs", 0)),
            "isolated_nodes": _to_int(verification_metrics.get("isolated_nodes", 0)),
            "invalid_port_refs": _to_int(verification_metrics.get("invalid_port_refs", 0)),
        },
        "repair_round_count": len(repair_history),
        "repair_scopes_seen": repair_scopes_seen,
        "final_route_decision": final_route_decision,
        "retry_exhausted": retry_exhausted,
        "retry_counts_by_scope": retry_counts_by_scope,
        "last_repair_issue_ids": last_repair_issue_ids,
        "last_repair_actions": last_repair_actions,
        "reject_reason": reject_reason,
        "repair_reject_category": repair_reject_category,
        "failure_bucket": failure_bucket,
        "hitl_stage": hitl_stage,
        "review_enabled": review_enabled,
        "review_required": review_required,
        "review_status": review_status,
        "review_id": review_id or str(review_request.get("review_id", "") or str(review_response.get("review_id", "") or "")).strip(),
        "review_history_count": len(review_history),
        "approval_record_json": str(approval_record_json or "").strip(),
        "compile_report_summary": {
            "page_count": _to_int(compile_report.get("page_count", 0)),
            "subflow_count": _to_int(compile_report.get("subflow_count", 0)),
            "node_count": _to_int(compile_report.get("node_count", 0)),
        },
        "acceptance_summary": acceptance_summary,
    }


def _wrap_node(node_name: str, node_callable: Callable[[dict], dict], node_io_records: list[dict]) -> Callable[[dict], dict]:
    def wrapped(state: dict) -> dict:
        input_snapshot = _make_serializable(copy.deepcopy(state))
        started_at = datetime.now()
        start_time = time.time()
        status = "success"
        result = state

        try:
            result = node_callable(state)
            output_snapshot = _make_serializable(copy.deepcopy(result))
        except GraphInterrupt:
            output_snapshot = {
                "interrupt_type": "GraphInterrupt",
                "hitl_stage": str((state or {}).get("hitl_stage", "") or "").strip(),
                "review_id": str((state or {}).get("review_id", "") or "").strip(),
            }
            status = "interrupted"
            raise
        except Exception as exc:
            output_snapshot = {
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
            status = "error"
            raise
        finally:
            elapsed_seconds = round(time.time() - start_time, 2)
            node_io_records.append({
                "node_index": len(node_io_records) + 1,
                "node_name": node_name,
                "status": status,
                "started_at": started_at.strftime("%Y-%m-%d %H:%M:%S"),
                "elapsed_seconds": elapsed_seconds,
                "changed_fields": _get_changed_fields(input_snapshot, output_snapshot) if status == "success" else [],
                "input": input_snapshot,
                "output": output_snapshot,
            })

        return result

    return wrapped


def _save_workflow_trace(
    user_query: str,
    node_io_records: list[dict],
    final_state: dict,
    total_elapsed_seconds: float,
    *,
    thread_id: str | None = None,
    attempt_id: str | None = None,
) -> dict:
    attempt_token = str(attempt_id or "").strip() or generate_attempt_id()
    trace_dir = os.path.join(TRACE_OUTPUT_ROOT, f"workflow_trace_{attempt_token}")
    os.makedirs(trace_dir, exist_ok=True)
    summary_json_path = os.path.join(trace_dir, "workflow_node_io_record.json")
    summary_md_path = os.path.join(trace_dir, "workflow_node_io_record.md")
    final_state_path = os.path.join(trace_dir, "final_state.json")

    review_files = save_review_artifacts(
        trace_output_root=TRACE_OUTPUT_ROOT,
        trace_dir=trace_dir,
        thread_id=thread_id,
        attempt_id=attempt_token,
        review_history=list((final_state or {}).get("review_history", []) or []),
        trace_files={
            "trace_dir": os.path.abspath(trace_dir),
            "summary_json": os.path.abspath(summary_json_path),
            "summary_md": os.path.abspath(summary_md_path),
            "final_state_json": os.path.abspath(final_state_path),
        },
    )

    trace_summary = _build_trace_summary(
        user_query=user_query,
        node_io_records=node_io_records,
        final_state=final_state,
        total_elapsed_seconds=total_elapsed_seconds,
        thread_id=thread_id,
        attempt_id=attempt_token,
        approval_record_json=str(review_files.get("approval_record_json", "") or "").strip(),
    )
    summary = dict(trace_summary)
    summary["nodes"] = node_io_records

    with open(summary_json_path, "w", encoding="utf-8") as file:
        json.dump(summary, file, ensure_ascii=False, indent=2)

    with open(final_state_path, "w", encoding="utf-8") as file:
        json.dump(_make_serializable(final_state), file, ensure_ascii=False, indent=2)

    markdown_lines = [
        "# 工作流节点输入输出记录\n",
        f"**执行时间**: {summary['execution_time']}\n",
        f"**用户需求**: {user_query}\n",
        f"**thread_id**: {summary['thread_id'] or 'N/A'}\n",
        f"**attempt_id**: {summary['attempt_id'] or 'N/A'}\n",
        f"**总耗时**: {summary['total_elapsed_seconds']}s\n",
        f"**节点数量**: {len(node_io_records)}\n",
        f"**工作流状态**: {summary['workflow_status']}\n",
        f"**最后成功节点**: {summary['last_successful_node'] or 'N/A'}\n",
        f"**失败节点**: {summary['failed_node'] or 'N/A'}\n",
        f"**Pattern**: {summary['selected_case_pattern_id'] or 'N/A'}\n",
        (
            f"**检索摘要**: atomic={summary['retrieved_atomic_count']} / "
            f"subflow={summary['retrieved_subflow_count']} / "
            f"pattern={summary['retrieved_pattern_count']}\n"
        ),
        (
            f"**检索诊断**: rewrite_used={summary['rewrite_used']} / "
            f"analysis_used={summary['analysis_used']} / "
            f"query_variants={summary['query_variants_count']} / "
            f"llm_queries={summary['llm_queries_count']} / "
            f"analysis_confidence={summary['analysis_confidence']}\n"
        ),
        (
            f"**检索 Top IDs**: subflow={', '.join(summary['top_subflow_template_ids']) if summary['top_subflow_template_ids'] else 'none'} / "
            f"pattern={', '.join(summary['top_system_pattern_ids']) if summary['top_system_pattern_ids'] else 'none'}\n"
        ),
        (
            f"**子系统实现**: reuse_template={summary['reuse_template_subsystem_count']} / "
            f"atomic_assembly={summary['atomic_assembly_subsystem_count']} / "
            f"subsystem_ids={', '.join(summary['subsystem_ids']) if summary['subsystem_ids'] else 'none'}\n"
        ),
        (
            f"**未解析项**: total={summary['unresolved_item_count']} / "
            f"errors={summary['unresolved_error_count']} / "
            f"warnings={summary['unresolved_warning_count']} / "
            f"types={', '.join(summary['unresolved_item_types']) if summary['unresolved_item_types'] else 'none'}\n"
        ),
        (
            f"**Planning 未解析分类**: "
            f"{', '.join(f'{key}={value}' for key, value in summary['planning_unresolved_by_type'].items()) if summary['planning_unresolved_by_type'] else 'none'} / "
            f"ambiguous_signal_count={summary['ambiguous_signal_count']}\n"
        ),
        (
            f"**验收摘要**: status={summary['verification_status'] or 'N/A'} / "
            f"scope={summary['verification_repair_scope'] or 'N/A'} / "
            f"errors={summary['verification_error_count']} / "
            f"warnings={summary['verification_warning_count']}\n"
        ),
        (
            f"**Repair 摘要**: rounds={summary['repair_round_count']} / "
            f"scopes={', '.join(summary['repair_scopes_seen']) if summary['repair_scopes_seen'] else 'none'} / "
            f"final_route={summary['final_route_decision'] or 'N/A'} / "
            f"retry_exhausted={summary['retry_exhausted']}\n"
        ),
        (
            f"**Scope 重试计数**: planning={summary['retry_counts_by_scope']['planning']} / "
            f"assembly={summary['retry_counts_by_scope']['assembly']} / "
            f"compile={summary['retry_counts_by_scope']['compile']}\n"
        ),
        f"**验收结论**: {summary['verification_issue_summary'] or summary['acceptance_summary']}\n",
        (
            f"**关键指标**: missing_required_inputs={summary['verification_metrics']['missing_required_inputs']} / "
            f"isolated_nodes={summary['verification_metrics']['isolated_nodes']} / "
            f"invalid_port_refs={summary['verification_metrics']['invalid_port_refs']}\n"
        ),
        (
            f"**编译计数**: pages={summary['compile_report_summary']['page_count']} / "
            f"subflows={summary['compile_report_summary']['subflow_count']} / "
            f"nodes={summary['compile_report_summary']['node_count']}\n"
        ),
    ]

    if summary["error_type"] or summary["error_message"]:
        markdown_lines.extend([
            f"**错误类型**: {summary['error_type'] or 'N/A'}\n",
            f"**错误信息**: {summary['error_message'] or 'N/A'}\n",
        ])

    markdown_lines.append(
        f"**Review 摘要**: stage={summary['hitl_stage']} / enabled={summary['review_enabled']} / "
        f"required={summary['review_required']} / status={summary['review_status']} / "
        f"review_id={summary['review_id'] or 'N/A'} / history={summary['review_history_count']}\n"
    )
    if summary["approval_record_json"]:
        markdown_lines.append(f"**Review 记录**: {summary['approval_record_json']}\n")

    if summary["last_repair_issue_ids"]:
        markdown_lines.append(f"**最近修复问题**: {', '.join(summary['last_repair_issue_ids'])}\n")

    if summary["last_repair_actions"]:
        markdown_lines.append(f"**最近修复动作**: {'；'.join(summary['last_repair_actions'])}\n")

    if summary["reject_reason"]:
        markdown_lines.append(f"**Reject 原因**: {summary['reject_reason']}\n")
    if summary["repair_reject_category"]:
        markdown_lines.append(f"**Reject 分类**: {summary['repair_reject_category']}\n")
    if summary["failure_bucket"]:
        markdown_lines.append(f"**Failure Bucket**: {summary['failure_bucket']}\n")

    markdown_lines.extend([
        f"**运行目录**: {os.path.abspath(trace_dir)}\n",
        "---\n",
    ])

    for record in node_io_records:
        markdown_lines.append(f"## {record['node_index']}. 节点: {record['node_name']}\n")
        markdown_lines.append(f"**状态**: {record['status']}\n")
        markdown_lines.append(f"**开始时间**: {record['started_at']}\n")
        markdown_lines.append(f"**耗时**: {record['elapsed_seconds']}s\n")

        if record["changed_fields"]:
            markdown_lines.append("**变更字段**:\n")
            for field in record["changed_fields"]:
                markdown_lines.append(f"- `{field}`\n")
            markdown_lines.append("\n")

        markdown_lines.append("### 输入\n")
        markdown_lines.append("```json")
        markdown_lines.append(json.dumps(_truncate_for_display(record["input"]), ensure_ascii=False, indent=2))
        markdown_lines.append("```\n")

        markdown_lines.append("### 输出\n")
        markdown_lines.append("```json")
        markdown_lines.append(json.dumps(_truncate_for_display(record["output"]), ensure_ascii=False, indent=2))
        markdown_lines.append("```\n")
        markdown_lines.append("---\n")

    with open(summary_md_path, "w", encoding="utf-8") as file:
        file.write("\n".join(markdown_lines))

    trace_files = {
        "thread_id": str(thread_id or "").strip(),
        "attempt_id": attempt_token,
        "trace_dir": os.path.abspath(trace_dir),
        "summary_json": os.path.abspath(summary_json_path),
        "summary_md": os.path.abspath(summary_md_path),
        "final_state_json": os.path.abspath(final_state_path),
        "review_records_json": str(review_files.get("review_records_json", "") or "").strip(),
        "approval_record_json": str(review_files.get("approval_record_json", "") or "").strip(),
    }
    normalized_thread_id = str(thread_id or "").strip()
    if normalized_thread_id:
        trace_files.update(
            register_trace_attempt(
                trace_output_root=TRACE_OUTPUT_ROOT,
                thread_id=normalized_thread_id,
                attempt_id=attempt_token,
                trace_files=trace_files,
            )
        )
        trace_files["review_attempt_index_json"] = str(review_files.get("review_attempt_index_json", "") or "").strip()
        trace_files["review_thread_index_json"] = str(review_files.get("review_thread_index_json", "") or "").strip()
        if review_files.get("review_record_jsons"):
            trace_files["review_record_jsons"] = list(review_files.get("review_record_jsons", []) or [])
    return trace_files


@traceable(name="create_workflow_trace", tags=["workflow", "langgraph", "trace"])
def create_workflow(
    *,
    checkpointer: Any | None = None,
    node_io_records: list[dict] | None = None,
) -> StateGraph:
    if RetrievalAgent is None:
        raise ImportError("RetrievalAgent 依赖未安装，无法创建正式工作流。")

    analysis_agent = AnalysisAgent()
    ambiguity_router = AmbiguityRouter()
    retrieval_agent = RetrievalAgent()
    clarification_review = ClarificationReviewAgent()
    clarification_apply = ClarificationApplyAgent()
    architecture_planner = ArchitecturePlanner()
    architecture_review = ArchitectureReviewAgent()
    architecture_feedback_apply = ArchitectureFeedbackApplyAgent()
    subsystem_planner = SubsystemPlanner()
    global_assembler = GlobalAssembler()
    coding_agent = CodingAgent()
    verifier_agent = VerifierAgent()
    repair_router = RepairRouter()
    repair_agent = RepairAgent()

    if node_io_records is None:
        node_io_records = []

    workflow = StateGraph(WorkflowState)
    return populate_phase4_workflow(
        workflow,
        {
            "analysis": _wrap_node("analysis", analysis_agent, node_io_records),
            "ambiguity_router": _wrap_node("ambiguity_router", ambiguity_router, node_io_records),
            "clarification_review": _wrap_node("clarification_review", clarification_review, node_io_records),
            "clarification_apply": _wrap_node("clarification_apply", clarification_apply, node_io_records),
            "retrieval": _wrap_node("retrieval", retrieval_agent, node_io_records),
            "architecture_planning": _wrap_node("architecture_planning", architecture_planner, node_io_records),
            "architecture_review": _wrap_node("architecture_review", architecture_review, node_io_records),
            "architecture_feedback_apply": _wrap_node(
                "architecture_feedback_apply",
                architecture_feedback_apply,
                node_io_records,
            ),
            "subsystem_planning": _wrap_node("subsystem_planning", subsystem_planner, node_io_records),
            "global_assembly": _wrap_node("global_assembly", global_assembler, node_io_records),
            "coding": _wrap_node("coding", coding_agent, node_io_records),
            "verification": _wrap_node("verification", verifier_agent, node_io_records),
            "repair_router": _wrap_node("repair_router", repair_router, node_io_records),
            "repair_agent": _wrap_node("repair_agent", repair_agent, node_io_records),
        },
        enable_repair_loop=True,
    )


@traceable(name="run_workflow_trace", tags=["workflow", "langgraph", "trace"])
def run_workflow(
    user_query: str,
    *,
    thread_id: str | None = None,
    checkpointer: Any | None = None,
    runtime_metadata: dict[str, Any] | None = None,
    enable_hitl_clarification: bool = False,
    enable_hitl_architecture_review: bool = False,
) -> dict:
    node_io_records: list[dict] = []
    started_at = time.time()
    attempt_id = generate_attempt_id()

    workflow = create_workflow(checkpointer=checkpointer, node_io_records=node_io_records)
    app = compile_state_graph(workflow, checkpointer=checkpointer)

    initial_state = build_initial_state(
        user_query,
        enable_hitl_clarification=bool(
            enable_hitl_clarification and checkpointer is not None and str(thread_id or "").strip()
        ),
        enable_hitl_architecture_review=bool(
            enable_hitl_architecture_review and checkpointer is not None and str(thread_id or "").strip()
        ),
    )

    invoke_config = build_runtime_invoke_config(
        user_query=user_query,
        run_name="MideaWorkflowTrace",
        tags=["workflow", "langgraph", "phase3-layered-planning", "trace"],
        recursion_limit=PHASE4_RECURSION_LIMIT,
        thread_id=thread_id,
        checkpointer=checkpointer,
        extra_metadata=runtime_metadata,
    )
    invoke_config["metadata"]["attempt_id"] = attempt_id

    result = None
    try:
        result = app.invoke(initial_state, config=invoke_config)
        return result
    finally:
        final_state = result if result is not None else initial_state
        trace_files = _save_workflow_trace(
            user_query=user_query,
            node_io_records=node_io_records,
            final_state=final_state,
            total_elapsed_seconds=time.time() - started_at,
            thread_id=thread_id,
            attempt_id=attempt_id,
        )

        if result is not None:
            result.setdefault("final_output", {})
            result["final_output"]["workflow_trace"] = trace_files


if __name__ == "__main__":
    query = "生成一个程序，接收一个输入，输入5v的时候，输出1，输入3v的时候输出2，输入10v的时候输出0"
    result = run_workflow(query)

    print("=" * 60)
    print("Trace workflow completed")
    print("=" * 60)
    print(f"Current step: {result.get('current_step')}")
    if result.get("verification_report"):
        report = result["verification_report"]
        print(f"Verification status: {report.get('status')}")
        print(f"Issues: {len(report.get('issues', []))}")
        print(f"Warnings: {len(report.get('warnings', []))}")
    trace_info = result.get("final_output", {}).get("workflow_trace", {})
    if trace_info:
        print(f"Trace dir: {trace_info.get('trace_dir')}")
