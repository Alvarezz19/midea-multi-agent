from __future__ import annotations

from typing import Any

from app.repositories.workflow_run_repository import AttemptRecord, ThreadRecord


TRACE_SUMMARY_KEYS = [
    "execution_time",
    "workflow_status",
    "failed_node",
    "last_successful_node",
    "node_count",
    "total_elapsed_seconds",
    "selected_case_pattern_id",
    "retrieved_atomic_count",
    "retrieved_subflow_count",
    "retrieved_pattern_count",
    "top_subflow_template_ids",
    "top_system_pattern_ids",
    "reuse_template_subsystem_count",
    "atomic_assembly_subsystem_count",
    "subsystem_ids",
    "unresolved_item_count",
    "unresolved_item_types",
    "planning_unresolved_by_type",
    "ambiguous_signal_count",
    "verification_status",
    "verification_repair_scope",
    "verification_issue_summary",
    "verification_error_count",
    "verification_warning_count",
    "verification_metrics",
    "repair_round_count",
    "repair_scopes_seen",
    "final_route_decision",
    "retry_exhausted",
    "retry_counts_by_scope",
    "review_status",
    "review_id",
    "hitl_stage",
    "failure_bucket",
    "acceptance_summary",
]


def infer_attempt_status(state: dict[str, Any] | None, *, fallback: str = "running") -> str:
    payload = dict(state or {})
    final_output = payload.get("final_output", {}) or {}
    route_decision = payload.get("route_decision", {}) or {}
    verification_report = payload.get("verification_report", {}) or {}
    review_request = payload.get("review_request", {}) or {}
    review_status = str(payload.get("review_status", "") or "").strip()

    if payload.get("__interrupt__") or (review_status == "pending" and review_request.get("stage")):
        return "interrupted"
    if route_decision.get("decision") == "reject" or final_output.get("review_abort"):
        return "rejected"
    if route_decision.get("decision") == "accept" or verification_report.get("status") == "passed":
        return "completed"
    return fallback


def build_review_projection(state: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(state or {})
    request = payload.get("review_request", {}) or {}
    return {
        "review_id": str(payload.get("review_id", "") or request.get("review_id", "") or "").strip(),
        "stage": str(request.get("stage", "") or payload.get("hitl_stage", "") or "none").strip() or "none",
        "status": str(payload.get("review_status", "") or "none").strip() or "none",
        "question": str(request.get("question", "") or "").strip(),
        "options": list(request.get("options", []) or []),
        "context_summary": str(request.get("context_summary", "") or "").strip(),
    }


def build_diagnostics_projection(state: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(state or {})
    verification_report = payload.get("verification_report", {}) or {}
    route_decision = payload.get("route_decision", {}) or {}
    return {
        "verification_status": str(verification_report.get("status", "") or "").strip(),
        "verification_issue_summary": str(verification_report.get("issue_summary", "") or "").strip(),
        "repair_round_count": len(list(payload.get("repair_history", []) or [])),
        "retry_counts_by_scope": dict(payload.get("retry_counts_by_scope", {}) or {}),
        "final_route_decision": str(route_decision.get("decision", "") or "").strip(),
    }


def build_progress_projection(state: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(state or {})
    trace = ((payload.get("final_output", {}) or {}).get("workflow_trace", {}) or {})
    return {
        "current_step_label": str(payload.get("current_step", "") or "start").strip() or "start",
        "last_successful_node": str(trace.get("last_successful_node", "") or "").strip(),
        "node_count": int(trace.get("node_count", 0) or 0),
    }


def build_attempt_detail(attempt: AttemptRecord, state: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(state or attempt.latest_state or {})
    status = infer_attempt_status(payload, fallback=attempt.status)
    trace_files = dict(((payload.get("final_output", {}) or {}).get("workflow_trace", {}) or {}) or attempt.trace_files)
    return {
        "thread_id": attempt.thread_id,
        "attempt_id": attempt.attempt_id,
        "status": status,
        "current_step": str(payload.get("current_step", "") or attempt.current_step or "start").strip() or "start",
        "workflow_status": str(payload.get("workflow_status", "") or attempt.workflow_status or "").strip(),
        "user_query": attempt.user_query,
        "review": build_review_projection(payload),
        "progress": build_progress_projection(payload),
        "diagnostics": build_diagnostics_projection(payload),
        "trace_files": trace_files,
        "subtasks": [],
    }


def build_attempt_result(attempt: AttemptRecord, state: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(state or attempt.latest_state or {})
    final_output = payload.get("final_output", {}) or {}
    trace_files = dict((final_output.get("workflow_trace", {}) or {}) or attempt.trace_files)
    return {
        "thread_id": attempt.thread_id,
        "attempt_id": attempt.attempt_id,
        "status": infer_attempt_status(payload, fallback=attempt.status),
        "result": {
            "json_text": str(final_output.get("json_text", "") or ""),
            "compile_report": dict(final_output.get("compile_report", {}) or {}),
            "verification_report": dict(final_output.get("verification_report", {}) or {}),
        },
        "trace_files": trace_files,
    }


def build_attempt_list_item(attempt: AttemptRecord) -> dict[str, Any]:
    return {
        "attempt_id": attempt.attempt_id,
        "status": attempt.status,
        "current_step": attempt.current_step,
        "started_at": attempt.created_at,
        "finished_at": attempt.finished_at,
        "verification_status": attempt.verification_status,
        "final_route_decision": attempt.final_route_decision,
    }


def build_trace_projection(
    attempt: AttemptRecord,
    state: dict[str, Any] | None = None,
    trace_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(state or attempt.latest_state or {})
    trace_files = dict(((payload.get("final_output", {}) or {}).get("workflow_trace", {}) or {}) or attempt.trace_files)
    summary_source = dict(trace_summary or {})
    summary = {key: summary_source.get(key) for key in TRACE_SUMMARY_KEYS if key in summary_source}
    if "node_count" not in summary:
        summary["node_count"] = len(list(summary_source.get("nodes", []) or []))
    if "workflow_status" not in summary:
        summary["workflow_status"] = infer_attempt_status(payload, fallback=attempt.status)
    return {
        "thread_id": attempt.thread_id,
        "attempt_id": attempt.attempt_id,
        "status": infer_attempt_status(payload, fallback=attempt.status),
        "current_step": str(payload.get("current_step", "") or attempt.current_step or "start").strip() or "start",
        "summary": summary,
        "review": build_review_projection(payload),
        "diagnostics": build_diagnostics_projection(payload),
        "trace_files": trace_files,
    }


def build_state_history_projection(
    *,
    thread_id: str,
    attempt_id: str,
    snapshots: list[dict[str, Any]],
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for snapshot in snapshots:
        values = dict(snapshot.get("values", {}) or {})
        items.append(
            {
                "created_at": str(snapshot.get("created_at", "") or ""),
                "next": list(snapshot.get("next", []) or []),
                "metadata": dict(snapshot.get("metadata", {}) or {}),
                "state": {
                    "current_step": str(values.get("current_step", "") or "").strip(),
                    "review_status": str(values.get("review_status", "") or "").strip(),
                    "review_id": str(values.get("review_id", "") or "").strip(),
                    "hitl_stage": str(values.get("hitl_stage", "") or "").strip(),
                    "verification_status": str((values.get("verification_report", {}) or {}).get("status", "") or "").strip(),
                    "route_decision": str((values.get("route_decision", {}) or {}).get("decision", "") or "").strip(),
                },
            }
        )
    return {"thread_id": thread_id, "attempt_id": attempt_id, "items": items}


def build_thread_overview(thread: ThreadRecord, latest_attempt: AttemptRecord | None) -> dict[str, Any]:
    review = {
        "review_id": "",
        "stage": "none",
        "status": "none",
    }
    latest_current_step = ""
    if latest_attempt:
        latest_current_step = latest_attempt.current_step
        review = {
            "review_id": latest_attempt.review_id,
            "stage": latest_attempt.review_stage,
            "status": str(((latest_attempt.latest_state or {}).get("review_status", "") or "none")).strip() or "none",
        }
    return {
        "thread_id": thread.thread_id,
        "title": thread.title,
        "latest_attempt_id": thread.latest_attempt_id,
        "latest_status": thread.latest_status,
        "latest_current_step": latest_current_step,
        "updated_at": thread.updated_at,
        "latest_review": review,
    }
