from __future__ import annotations

import argparse
import json
import sys
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import workflow_trace
from scripts.phase6_shared import (
    CASE_FILE_PATH,
    REAL_QUERY_SUITE_OUTPUT_ROOT,
    Phase6RealQueryCase,
    load_phase6_cases,
    timestamp_token,
    update_marker,
    write_json,
    write_text,
)
from utils.phase6_diagnostics import derive_end_state, derive_failure_bucket, ordered_subsystem_ids


REBASELINE_EXPECTATION_DIAGNOSES = {
    "expected_repair_but_direct_pass",
    "expected_reject_but_direct_pass",
    "expected_reject_but_repair_then_passed",
}


def _read_json(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    target = Path(path)
    if not target.exists():
        return {}
    return json.loads(target.read_text(encoding="utf-8"))


def _discover_trace_info(trace_output_root: str | Path | None, before_dirs: set[str]) -> dict[str, str]:
    if trace_output_root is None:
        return {}

    root = Path(trace_output_root)
    if not root.exists():
        return {}

    candidates = [
        candidate
        for candidate in root.glob("workflow_trace_*")
        if candidate.is_dir() and str(candidate.resolve()) not in before_dirs
    ]
    if not candidates:
        candidates = [candidate for candidate in root.glob("workflow_trace_*") if candidate.is_dir()]
    if not candidates:
        return {}

    latest = max(candidates, key=lambda candidate: candidate.stat().st_mtime)
    summary_json = latest / "workflow_node_io_record.json"
    summary_md = latest / "workflow_node_io_record.md"
    final_state_json = latest / "final_state.json"
    return {
        "trace_dir": str(latest.resolve()),
        "summary_json": str(summary_json.resolve()) if summary_json.exists() else "",
        "summary_md": str(summary_md.resolve()) if summary_md.exists() else "",
        "final_state_json": str(final_state_json.resolve()) if final_state_json.exists() else "",
    }


def _trace_info_from_result(
    result: dict[str, Any] | None,
    *,
    trace_output_root: str | Path | None,
    before_dirs: set[str],
) -> dict[str, str]:
    if isinstance(result, dict):
        trace_info = ((result.get("final_output", {}) or {}).get("workflow_trace", {}) or {})
        if trace_info:
            return {
                "trace_dir": str(trace_info.get("trace_dir", "")).strip(),
                "summary_json": str(trace_info.get("summary_json", "")).strip(),
                "summary_md": str(trace_info.get("summary_md", "")).strip(),
                "final_state_json": str(trace_info.get("final_state_json", "")).strip(),
            }
    return _discover_trace_info(trace_output_root, before_dirs)


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _expectation_diagnosis(
    case: Phase6RealQueryCase,
    actual: dict[str, Any],
    *,
    case_passed: bool,
) -> str:
    actual_end_state = str(actual.get("actual_end_state", "")).strip()
    verification_status = str(actual.get("verification_status", "")).strip()
    route_decision = str(actual.get("route_decision", "")).strip()
    failure_bucket = str(actual.get("failure_bucket", "")).strip()

    if failure_bucket == "unexpected_exception":
        return "unexpected_exception"

    if case.case_type == "golden_success":
        return "matched_expectation" if case_passed else "golden_regression"

    if case.case_type == "observed_success":
        return "matched_expectation" if case_passed else "observed_success_regression"

    if case.case_type == "expected_repair":
        if actual_end_state == "passed" and verification_status == "passed" and route_decision == "accept":
            return "expected_repair_but_direct_pass"
        if case_passed:
            return "matched_expectation"
        if route_decision == "reject" and actual_end_state.startswith("rejected_"):
            return "expected_repair_but_rejected"
        return "expected_repair_other_mismatch"

    if route_decision == "accept" and actual_end_state == "passed" and verification_status == "passed":
        return "expected_reject_but_direct_pass"
    if actual_end_state == "passed_after_repair" or failure_bucket == "repair_then_passed":
        return "expected_reject_but_repair_then_passed"
    if case_passed:
        return "matched_expectation"
    if route_decision == "reject" and actual_end_state.startswith("rejected_"):
        return "expected_reject_wrong_failure_bucket"
    return "expected_reject_other_mismatch"


def _summary_from_result(
    case: Phase6RealQueryCase,
    result: dict[str, Any] | None,
    trace_info: dict[str, str],
    trace_summary: dict[str, Any],
    exception: Exception | None,
) -> dict[str, Any]:
    result = result or {}
    verification_report = result.get("verification_report", {}) or {}
    route_decision = result.get("route_decision", {}) or {}
    repair_history = list(result.get("repair_history", []) or [])
    retrieval_bundle = result.get("retrieval_bundle", {}) or {}
    retrieval_metadata = retrieval_bundle.get("metadata", {}) if isinstance(retrieval_bundle.get("metadata"), dict) else {}
    subsystem_plan_map = result.get("subsystem_plan_map", {}) or {}
    architecture_plan = result.get("architecture_plan", {}) or {}

    unresolved_item_types = list(trace_summary.get("unresolved_item_types", []) or [])
    if not unresolved_item_types:
        unresolved_item_types = sorted(
            {
                str((item or {}).get("type", "")).strip()
                for item in ((result.get("assembled_graph_ir", {}) or {}).get("unresolved_items", []) or [])
                if str((item or {}).get("type", "")).strip()
            }
        )

    repair_reject_category = str(trace_summary.get("repair_reject_category", "")).strip()
    error_type = str(trace_summary.get("error_type", "")).strip()
    error_message = str(trace_summary.get("error_message", "")).strip()
    if exception is not None and not error_type:
        error_type = type(exception).__name__
    if exception is not None and not error_message:
        error_message = str(exception)

    failure_bucket = str(trace_summary.get("failure_bucket", "")).strip() or derive_failure_bucket(
        verification_report=verification_report,
        route_decision=route_decision,
        repair_history=repair_history,
        unresolved_item_types=unresolved_item_types,
        repair_reject_category=repair_reject_category,
        workflow_status=str(trace_summary.get("workflow_status", "")).strip(),
        error_type=error_type,
        error_message=error_message,
    )
    route_decision_text = str(route_decision.get("decision", "")).strip()
    verification_status = str(verification_report.get("status", "")).strip()
    actual_end_state = derive_end_state(
        failure_bucket=failure_bucket,
        route_decision=route_decision_text,
        verification_status=verification_status,
    )

    subsystem_ids = list(trace_summary.get("subsystem_ids", []) or [])
    if not subsystem_ids:
        subsystem_ids = ordered_subsystem_ids(architecture_plan, subsystem_plan_map)

    return {
        "verification_status": verification_status,
        "repair_scope": str(verification_report.get("repair_scope", "")).strip(),
        "route_decision": route_decision_text,
        "failure_bucket": failure_bucket,
        "actual_end_state": actual_end_state,
        "selected_case_pattern_id": str(
            trace_summary.get("selected_case_pattern_id")
            or retrieval_metadata.get("selected_case_pattern_id", "")
        ).strip(),
        "retrieved_atomic_count": _as_int(
            trace_summary.get("retrieved_atomic_count", retrieval_metadata.get("retrieved_atomic_count", 0))
        ),
        "retrieved_subflow_count": _as_int(
            trace_summary.get("retrieved_subflow_count", retrieval_metadata.get("retrieved_subflow_count", 0))
        ),
        "retrieved_pattern_count": _as_int(
            trace_summary.get("retrieved_pattern_count", retrieval_metadata.get("retrieved_pattern_count", 0))
        ),
        "top_subflow_template_ids": list(
            trace_summary.get("top_subflow_template_ids", retrieval_metadata.get("top_subflow_template_ids", [])) or []
        ),
        "top_system_pattern_ids": list(
            trace_summary.get("top_system_pattern_ids", retrieval_metadata.get("top_system_pattern_ids", [])) or []
        ),
        "subsystem_ids": subsystem_ids,
        "unresolved_item_types": unresolved_item_types,
        "repair_round_count": _as_int(
            trace_summary.get("repair_round_count", len(repair_history))
        ),
        "trace_dir": str(trace_info.get("trace_dir", "")).strip(),
        "trace_summary_json": str(trace_info.get("summary_json", "")).strip(),
        "trace_summary_md": str(trace_info.get("summary_md", "")).strip(),
        "final_state_json": str(trace_info.get("final_state_json", "")).strip(),
        "repair_reject_category": repair_reject_category,
        "verification_issue_summary": str(verification_report.get("issue_summary", "")).strip(),
        "error_type": error_type,
        "error_message": error_message,
    }


def _evaluate_case(case: Phase6RealQueryCase, actual: dict[str, Any]) -> tuple[bool, list[str], list[str]]:
    failures: list[str] = []
    drifts: list[str] = []

    actual_end_state = str(actual.get("actual_end_state", "")).strip()
    if actual_end_state not in case.allowed_end_states:
        failures.append(
            f"allowed_end_states expected={list(case.allowed_end_states)} actual={actual_end_state or '<empty>'}"
        )

    missing_subsystems = [item for item in case.expected_subsystems if item not in set(actual.get("subsystem_ids", []))]
    if missing_subsystems:
        failures.append(f"expected_subsystems missing={', '.join(missing_subsystems)}")

    if _as_int(actual.get("retrieved_subflow_count")) < case.expected_min_subflow_count:
        failures.append(
            f"expected_min_subflow_count expected>={case.expected_min_subflow_count} "
            f"actual={_as_int(actual.get('retrieved_subflow_count'))}"
        )

    if _as_int(actual.get("repair_round_count")) > case.max_repair_rounds:
        failures.append(
            f"max_repair_rounds expected<={case.max_repair_rounds} actual={_as_int(actual.get('repair_round_count'))}"
        )

    if case.case_type == "expected_reject" and str(actual.get("failure_bucket", "")).strip() == "other_retryable_error":
        failures.append("expected_reject case 收敛到了 other_retryable_error")

    comparisons = {
        "verification_status": case.expected_verification_status,
        "route_decision": case.expected_route_decision,
        "failure_bucket": case.expected_failure_bucket,
    }
    for field_name, expected_value in comparisons.items():
        actual_value = str(actual.get(field_name, "")).strip()
        if actual_value != expected_value:
            message = f"{field_name} expected={expected_value} actual={actual_value}"
            if case.case_type == "golden_success":
                failures.append(message)
            else:
                drifts.append(message)

    return len(failures) == 0, failures, drifts


def _retention_action(case: Phase6RealQueryCase, actual: dict[str, Any], case_passed: bool) -> str:
    policy = case.golden_trace_policy
    if policy == "keep_always":
        return "keep_always"
    if policy == "keep_last_green" and case_passed:
        return "keep_last_green"
    if policy == "keep_last_failure" and not case_passed:
        return "keep_last_failure"
    return "no_force_keep"


def run_case(
    case: Phase6RealQueryCase,
    *,
    workflow_runner: Callable[[str], dict[str, Any]] | None = None,
    trace_output_root: str | Path | None = None,
) -> dict[str, Any]:
    runner = workflow_runner or workflow_trace.run_workflow
    trace_root = Path(trace_output_root) if trace_output_root is not None else None
    before_dirs = set()
    if trace_root is not None and trace_root.exists():
        before_dirs = {str(path.resolve()) for path in trace_root.glob("workflow_trace_*") if path.is_dir()}

    result: dict[str, Any] | None = None
    exception: Exception | None = None
    with ExitStack() as stack:
        if trace_root is not None:
            trace_root.mkdir(parents=True, exist_ok=True)
            stack.enter_context(patch.object(workflow_trace, "TRACE_OUTPUT_ROOT", str(trace_root)))
        try:
            result = runner(case.query)
        except Exception as exc:  # pragma: no cover - exercised by contract stubs
            exception = exc

    trace_info = _trace_info_from_result(result, trace_output_root=trace_output_root, before_dirs=before_dirs)
    trace_summary = _read_json(trace_info.get("summary_json"))
    actual = _summary_from_result(case, result, trace_info, trace_summary, exception)
    case_passed, failures, drifts = _evaluate_case(case, actual)
    expectation_diagnosis = _expectation_diagnosis(case, actual, case_passed=case_passed)
    retention_action = _retention_action(case, actual, case_passed)
    return {
        "case_id": case.case_id,
        "query": case.query,
        "case_type": case.case_type,
        "passed": case_passed,
        "failures": failures,
        "drifts": drifts,
        "expectation_diagnosis": expectation_diagnosis,
        "rebaseline_candidate": expectation_diagnosis in REBASELINE_EXPECTATION_DIAGNOSES,
        "expected": {
            "expected_subsystems": list(case.expected_subsystems),
            "expected_min_subflow_count": case.expected_min_subflow_count,
            "expected_verification_status": case.expected_verification_status,
            "expected_route_decision": case.expected_route_decision,
            "expected_failure_bucket": case.expected_failure_bucket,
            "allowed_end_states": list(case.allowed_end_states),
            "max_repair_rounds": case.max_repair_rounds,
            "golden_trace_policy": case.golden_trace_policy,
        },
        "actual": actual,
        "retention_action": retention_action,
        "notes": case.notes,
    }


def _update_retention_markers(
    output_root: Path,
    run_dir: Path,
    results: list[dict[str, Any]],
    *,
    all_passed: bool,
) -> dict[str, Any]:
    retention_root = output_root / "_retained"
    marker_payload = {
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "run_dir": str(run_dir.resolve()),
    }
    retained_case_refs: list[dict[str, Any]] = []

    for item in results:
        trace_dir = str((item.get("actual", {}) or {}).get("trace_dir", "")).strip()
        if not trace_dir:
            continue
        action = str(item.get("retention_action", "no_force_keep")).strip()
        case_id = item["case_id"]
        case_marker_payload = {
            **marker_payload,
            "case_id": case_id,
            "retention_action": action,
            "trace_dir": trace_dir,
            "trace_summary_json": (item.get("actual", {}) or {}).get("trace_summary_json", ""),
            "trace_summary_md": (item.get("actual", {}) or {}).get("trace_summary_md", ""),
        }
        if action == "keep_always":
            marker_path = retention_root / "golden" / f"{case_id}.json"
        elif action == "keep_last_green":
            marker_path = retention_root / "last_green" / f"{case_id}.json"
        elif action == "keep_last_failure":
            marker_path = retention_root / "last_failure" / f"{case_id}.json"
        else:
            continue
        update_marker(marker_path, case_marker_payload)
        retained_case_refs.append({
            "case_id": case_id,
            "marker_path": str(marker_path.resolve()),
            "trace_dir": trace_dir,
            "retention_action": action,
        })

    run_marker_path = retention_root / ("latest_green_run.json" if all_passed else "latest_failure_run.json")
    update_marker(
        run_marker_path,
        {
            **marker_payload,
            "all_passed": all_passed,
            "case_count": len(results),
        },
    )
    return {
        "run_marker": str(run_marker_path.resolve()),
        "retained_case_refs": retained_case_refs,
    }


def _write_suite_markdown(run_dir: Path, suite_summary: dict[str, Any]) -> Path:
    lines = [
        "# Phase 6 Real Query Suite",
        "",
        f"- 生成时间：{suite_summary['generated_at']}",
        f"- case_count：{suite_summary['case_count']}",
        f"- passed_count：{suite_summary['passed_count']}",
        f"- failed_count：{suite_summary['failed_count']}",
        f"- repair_then_passed_count：{suite_summary['repair_then_passed_count']}",
        f"- rejected_count：{suite_summary['rejected_count']}",
        f"- unexpected_exception_count：{suite_summary['unexpected_exception_count']}",
        f"- golden_case_pass_rate：`{suite_summary['golden_case_pass_rate']}`",
        f"- golden_threshold_met：`{suite_summary['golden_threshold_met']}`",
        f"- drift_case_count：`{suite_summary['drift_case_count']}`",
        f"- rebaseline_candidate_count：`{suite_summary['rebaseline_candidate_count']}`",
        f"- all_passed：`{suite_summary['all_passed']}`",
        f"- run_dir：`{suite_summary['run_dir']}`",
        "",
        "## Failure Bucket Counts",
        "",
    ]
    for bucket_name, count in sorted((suite_summary.get("failure_bucket_counts", {}) or {}).items()):
        lines.append(f"- {bucket_name}: `{count}`")

    lines.extend(["", "## Expectation Diagnosis Counts", ""])
    for diagnosis, count in sorted((suite_summary.get("expectation_diagnosis_counts", {}) or {}).items()):
        lines.append(f"- {diagnosis}: `{count}`")

    if suite_summary.get("rebaseline_candidate_case_ids"):
        lines.extend([
            "",
            "## Rebaseline Candidates",
            "",
            f"- case_ids: `{', '.join(suite_summary['rebaseline_candidate_case_ids'])}`",
        ])

    if suite_summary.get("failed_case_ids"):
        lines.extend([
            "",
            "## Contract Failed Cases",
            "",
            f"- case_ids: `{', '.join(suite_summary['failed_case_ids'])}`",
        ])

    lines.extend(["", "## Case Results", ""])
    for item in suite_summary["results"]:
        actual = item["actual"]
        lines.extend(
            [
                f"### {item['case_id']}",
                f"- case_type: `{item['case_type']}`",
                f"- query: `{item['query']}`",
                f"- passed: `{item['passed']}`",
                f"- expectation_diagnosis: `{item['expectation_diagnosis']}`",
                f"- rebaseline_candidate: `{item['rebaseline_candidate']}`",
                f"- verification_status: `{actual['verification_status']}`",
                f"- route_decision: `{actual['route_decision']}`",
                f"- failure_bucket: `{actual['failure_bucket']}`",
                f"- actual_end_state: `{actual['actual_end_state']}`",
                f"- repair_scope: `{actual['repair_scope']}`",
                f"- repair_round_count: `{actual['repair_round_count']}`",
                f"- selected_case_pattern_id: `{actual['selected_case_pattern_id'] or 'N/A'}`",
                f"- subsystem_ids: `{', '.join(actual['subsystem_ids']) if actual['subsystem_ids'] else 'none'}`",
                f"- unresolved_item_types: `{', '.join(actual['unresolved_item_types']) if actual['unresolved_item_types'] else 'none'}`",
                f"- top_subflow_template_ids: `{', '.join(actual['top_subflow_template_ids']) if actual['top_subflow_template_ids'] else 'none'}`",
                f"- top_system_pattern_ids: `{', '.join(actual['top_system_pattern_ids']) if actual['top_system_pattern_ids'] else 'none'}`",
                f"- trace_dir: `{actual['trace_dir'] or 'N/A'}`",
                f"- trace_summary_json: `{actual['trace_summary_json'] or 'N/A'}`",
                f"- trace_summary_md: `{actual['trace_summary_md'] or 'N/A'}`",
            ]
        )
        if item["failures"]:
            lines.append(f"- failures: `{'; '.join(item['failures'])}`")
        if item["drifts"]:
            lines.append(f"- drifts: `{'; '.join(item['drifts'])}`")
        lines.append("")

    summary_md = run_dir / "phase6_real_query_suite_summary.md"
    write_text(summary_md, "\n".join(lines))
    return summary_md


def run_suite(
    *,
    case_file_path: str | Path | None = None,
    output_root: str | Path | None = None,
    workflow_runner: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload, cases = load_phase6_cases(case_file_path=case_file_path)
    output_root_path = Path(output_root) if output_root is not None else REAL_QUERY_SUITE_OUTPUT_ROOT
    run_dir = output_root_path / f"suite_{timestamp_token()}"
    trace_output_root = run_dir / "workflow_traces"
    run_dir.mkdir(parents=True, exist_ok=True)

    results = [
        run_case(case, workflow_runner=workflow_runner, trace_output_root=trace_output_root)
        for case in cases
    ]

    golden_results = [item for item in results if item["case_type"] == "golden_success"]
    golden_passed_count = sum(1 for item in golden_results if item["passed"])
    golden_case_pass_rate = round(golden_passed_count / len(golden_results), 4) if golden_results else 0.0
    failure_bucket_counts: dict[str, int] = {}
    expectation_diagnosis_counts: dict[str, int] = {}
    expectation_diagnosis_case_ids: dict[str, list[str]] = {}
    for item in results:
        bucket = str((item.get("actual", {}) or {}).get("failure_bucket", "")).strip() or "other_retryable_error"
        failure_bucket_counts[bucket] = failure_bucket_counts.get(bucket, 0) + 1
        diagnosis = str(item.get("expectation_diagnosis", "")).strip() or "matched_expectation"
        expectation_diagnosis_counts[diagnosis] = expectation_diagnosis_counts.get(diagnosis, 0) + 1
        expectation_diagnosis_case_ids.setdefault(diagnosis, []).append(item["case_id"])

    summary_json_path = run_dir / "phase6_real_query_suite_summary.json"
    summary_md_path = run_dir / "phase6_real_query_suite_summary.md"
    suite_summary = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "schema_version": str(payload.get("schema_version", "")),
        "case_owner": str(payload.get("case_owner", "")),
        "case_file": str((Path(case_file_path) if case_file_path is not None else CASE_FILE_PATH).resolve()),
        "case_count": len(results),
        "passed_count": sum(1 for item in results if item["passed"]),
        "failed_count": sum(1 for item in results if not item["passed"]),
        "repair_then_passed_count": sum(
            1
            for item in results
            if str((item.get("actual", {}) or {}).get("failure_bucket", "")).strip() == "repair_then_passed"
        ),
        "rejected_count": sum(
            1
            for item in results
            if str((item.get("actual", {}) or {}).get("actual_end_state", "")).startswith("rejected_")
        ),
        "unexpected_exception_count": sum(
            1
            for item in results
            if str((item.get("actual", {}) or {}).get("failure_bucket", "")).strip() == "unexpected_exception"
        ),
        "drift_case_count": sum(1 for item in results if item["drifts"]),
        "rebaseline_candidate_count": sum(1 for item in results if item.get("rebaseline_candidate", False)),
        "failure_bucket_counts": failure_bucket_counts,
        "expectation_diagnosis_counts": expectation_diagnosis_counts,
        "expectation_diagnosis_case_ids": expectation_diagnosis_case_ids,
        "failed_case_ids": [item["case_id"] for item in results if not item["passed"]],
        "drift_case_ids": [item["case_id"] for item in results if item["drifts"]],
        "rebaseline_candidate_case_ids": [item["case_id"] for item in results if item.get("rebaseline_candidate", False)],
        "golden_case_count": len(golden_results),
        "golden_case_pass_rate": golden_case_pass_rate,
        "golden_threshold_met": golden_case_pass_rate >= 0.8,
        "run_dir": str(run_dir.resolve()),
        "summary_json": str(summary_json_path.resolve()),
        "summary_md": str(summary_md_path.resolve()),
        "results": results,
    }
    suite_summary["all_passed"] = bool(
        suite_summary["failed_count"] == 0 and suite_summary["golden_threshold_met"]
    )
    suite_summary["retention"] = _update_retention_markers(
        output_root_path,
        run_dir,
        results,
        all_passed=suite_summary["all_passed"],
    )

    write_json(summary_json_path, suite_summary)
    _write_suite_markdown(run_dir, suite_summary)
    return suite_summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Phase 6 real query suite.")
    parser.add_argument("--case-file", default=str(CASE_FILE_PATH), help="Phase 6 case file path.")
    parser.add_argument(
        "--output-root",
        default=str(REAL_QUERY_SUITE_OUTPUT_ROOT),
        help="Directory used to write phase6 real query suite outputs.",
    )
    args = parser.parse_args(argv)

    suite_summary = run_suite(
        case_file_path=args.case_file,
        output_root=args.output_root,
    )
    print(f"Phase 6 real query suite summary written to: {suite_summary['summary_md']}")
    for item in suite_summary["results"]:
        print(
            json.dumps(
                {
                    "case_id": item["case_id"],
                    "passed": item["passed"],
                    "actual_end_state": item["actual"]["actual_end_state"],
                    "failure_bucket": item["actual"]["failure_bucket"],
                    "trace_dir": item["actual"]["trace_dir"],
                },
                ensure_ascii=False,
            )
        )
    return 0 if suite_summary["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
