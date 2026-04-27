from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.retrieval_agent import RetrievalAgent
from scripts.phase6_shared import (
    CASE_FILE_PATH,
    RETRIEVAL_EVAL_OUTPUT_ROOT,
    Phase6RealQueryCase,
    build_retrieval_analysis_result,
    build_template_role_source_evidence,
    default_pattern_ids,
    load_pattern_library_assets,
    load_phase6_cases,
    resolve_template_roles,
    timestamp_token,
    update_marker,
    write_json,
    write_text,
)


def _as_string(value: Any) -> str:
    return str(value or "").strip()


def _as_float(value: Any) -> float:
    try:
        return round(float(value or 0.0), 4)
    except (TypeError, ValueError):
        return 0.0


def _unique_strings(values: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _as_string(value)
        if normalized and normalized not in seen:
            ordered.append(normalized)
            seen.add(normalized)
    return ordered


def _bundle_top_ids(bundle: dict[str, Any], metadata_key: str, item_key: str) -> list[str]:
    metadata = bundle.get("metadata", {}) if isinstance(bundle.get("metadata"), dict) else {}
    top_ids = metadata.get(metadata_key, [])
    if isinstance(top_ids, list) and top_ids:
        return [_as_string(item) for item in top_ids if _as_string(item)]
    ordered: list[str] = []
    for item in bundle.get(item_key, []) or []:
        if not isinstance(item, dict):
            continue
        identifier = _as_string(item.get("template_id") or item.get("pattern_id") or item.get("module_type"))
        if identifier:
            ordered.append(identifier)
        if len(ordered) >= 5:
            break
    return ordered


def _template_roles(bundle: dict[str, Any]) -> list[str]:
    roles: list[str] = []
    for item in bundle.get("subflow_templates", []) or []:
        if not isinstance(item, dict):
            continue
        role = _as_string(item.get("template_role"))
        if role:
            roles.append(role)
        if len(roles) >= 5:
            break
    return roles


def _match_template(item: dict[str, Any], expected_template_roles: list[str]) -> bool:
    role = _as_string(item.get("template_role"))
    template_id = _as_string(item.get("template_id") or item.get("module_type"))
    return role in expected_template_roles or template_id in expected_template_roles


def _template_hit(bundle: dict[str, Any], expected_template_roles: list[str], top_n: int) -> bool:
    if not expected_template_roles:
        return False
    for item in (bundle.get("subflow_templates", []) or [])[:top_n]:
        if isinstance(item, dict) and _match_template(item, expected_template_roles):
            return True
    return False


def _pattern_hit(bundle: dict[str, Any], expected_pattern_ids: list[str], top_n: int) -> bool:
    if not expected_pattern_ids:
        return False
    for item in (bundle.get("system_patterns", []) or [])[:top_n]:
        if not isinstance(item, dict):
            continue
        if _as_string(item.get("pattern_id")) in expected_pattern_ids:
            return True
    return False


def _template_exists(available_template_roles: set[str], expected_template_roles: list[str]) -> bool:
    if not expected_template_roles:
        return False
    return all(role in available_template_roles for role in expected_template_roles)


def _pattern_exists(available_pattern_ids: set[str], expected_pattern_ids: list[str]) -> bool:
    if not expected_pattern_ids:
        return False
    return all(pattern_id in available_pattern_ids for pattern_id in expected_pattern_ids)


def _missing_expected_items(available_items: set[str], expected_items: list[str]) -> list[str]:
    return [item for item in expected_items if item not in available_items]


def _asset_gap_reason(*, missing_template_roles: list[str], missing_pattern_ids: list[str]) -> str:
    if missing_template_roles and missing_pattern_ids:
        return "missing_template_and_pattern_assets"
    if missing_template_roles:
        return "missing_template_assets"
    if missing_pattern_ids:
        return "missing_pattern_assets"
    return ""


def _empty_role_diagnostic(template_role: str) -> dict[str, Any]:
    return {
        "template_role": template_role,
        "source_evidence_found": False,
        "source_subflow_candidate_found": False,
        "likely_gap_stage": "unknown",
        "source_pattern_page_keys": [],
        "source_pattern_page_labels": [],
        "source_flow_paths": [],
        "source_flow_page_labels": [],
        "matched_subflow_names": [],
        "matched_object_names": [],
        "adjacent_subflow_definition_names": [],
    }


def _aggregate_asset_gap_fields(
    results: list[dict[str, Any]],
    *,
    diagnosis_counts: dict[str, int],
    golden_results: list[dict[str, Any]],
) -> dict[str, Any]:
    asset_gap_template_role_case_ids: dict[str, list[str]] = {}
    asset_gap_pattern_id_case_ids: dict[str, list[str]] = {}
    asset_gap_case_type_counts: dict[str, int] = {}

    for item in results:
        if item["retrieval_diagnosis"] != "asset_gap":
            continue
        asset_gap_case_type_counts[item["case_type"]] = asset_gap_case_type_counts.get(item["case_type"], 0) + 1
        for template_role in _unique_strings(list(item.get("missing_template_roles", []))):
            asset_gap_template_role_case_ids.setdefault(template_role, []).append(item["case_id"])
        for pattern_id in _unique_strings(list(item.get("missing_pattern_ids", []))):
            asset_gap_pattern_id_case_ids.setdefault(pattern_id, []).append(item["case_id"])

    asset_gap_template_role_counts = {
        template_role: len(case_ids)
        for template_role, case_ids in asset_gap_template_role_case_ids.items()
    }
    asset_gap_pattern_id_counts = {
        pattern_id: len(case_ids)
        for pattern_id, case_ids in asset_gap_pattern_id_case_ids.items()
    }
    asset_gap_template_role_diagnostics = build_template_role_source_evidence(
        list(asset_gap_template_role_counts.keys())
    )

    for item in results:
        role_diagnostics = [
            dict(asset_gap_template_role_diagnostics.get(template_role, _empty_role_diagnostic(template_role)))
            for template_role in item.get("missing_template_roles", [])
        ]
        item["missing_template_role_diagnostics"] = role_diagnostics
        item["asset_gap_root_cause"] = ""
        item["asset_gap_source_flow_paths"] = []
        item["asset_gap_source_pattern_page_keys"] = []
        if role_diagnostics:
            root_causes = _unique_strings([diagnostic.get("likely_gap_stage", "") for diagnostic in role_diagnostics])
            item["asset_gap_root_cause"] = root_causes[0] if len(root_causes) == 1 else ";".join(root_causes)
            item["asset_gap_source_flow_paths"] = _unique_strings(
                [
                    path
                    for diagnostic in role_diagnostics
                    for path in diagnostic.get("source_flow_paths", [])
                ]
            )
            item["asset_gap_source_pattern_page_keys"] = _unique_strings(
                [
                    page_key
                    for diagnostic in role_diagnostics
                    for page_key in diagnostic.get("source_pattern_page_keys", [])
                ]
            )

    golden_asset_gap_case_ids = [
        item["case_id"]
        for item in golden_results
        if item["retrieval_diagnosis"] == "asset_gap"
    ]
    ready_for_c_blockers: list[str] = []
    if diagnosis_counts["metadata_insufficient"] > 0:
        ready_for_c_blockers.append("metadata_insufficient_present")
    if diagnosis_counts["query_coverage_gap"] > 0:
        ready_for_c_blockers.append("query_coverage_gap_present")
    if diagnosis_counts["ranking_issue"] > 0:
        ready_for_c_blockers.append("ranking_issue_present")
    if golden_asset_gap_case_ids:
        ready_for_c_blockers.append("golden_asset_gap_present")

    single_root_asset_gap = {
        "is_single_root_cause": bool(
            diagnosis_counts["asset_gap"] > 0
            and len(asset_gap_template_role_counts) == 1
            and not asset_gap_pattern_id_counts
        ),
        "template_role": next(iter(asset_gap_template_role_counts), ""),
        "case_count": diagnosis_counts["asset_gap"],
    }
    ready_for_c = not ready_for_c_blockers
    ready_for_c_reason = (
        "golden_retrieval_stable_with_single_known_nonblocking_asset_backlog"
        if ready_for_c and single_root_asset_gap["is_single_root_cause"] and diagnosis_counts["asset_gap"] > 0
        else "golden_retrieval_stable_without_known_asset_backlog"
        if ready_for_c
        else "retrieval_gates_not_met_for_work_package_c"
    )
    known_non_blocking_backlog = {
        "template_roles": list(asset_gap_template_role_counts.keys()) if ready_for_c else [],
        "case_ids": sorted({case_id for case_ids in asset_gap_template_role_case_ids.values() for case_id in case_ids})
        if ready_for_c
        else [],
        "role_diagnostics": asset_gap_template_role_diagnostics if ready_for_c else {},
    }
    preferred_next_step = (
        "continue_ab_diagnostic_closure"
        if ready_for_c and diagnosis_counts["asset_gap"] > 0
        else "enter_work_package_c"
        if ready_for_c
        else "continue_ab_diagnostic_closure"
    )

    return {
        "asset_gap_template_role_counts": asset_gap_template_role_counts,
        "asset_gap_template_role_case_ids": asset_gap_template_role_case_ids,
        "asset_gap_pattern_id_counts": asset_gap_pattern_id_counts,
        "asset_gap_pattern_id_case_ids": asset_gap_pattern_id_case_ids,
        "asset_gap_case_type_counts": asset_gap_case_type_counts,
        "asset_gap_template_role_diagnostics": asset_gap_template_role_diagnostics,
        "single_root_asset_gap": single_root_asset_gap,
        "ready_for_c": ready_for_c,
        "ready_for_c_reason": ready_for_c_reason,
        "ready_for_c_blockers": ready_for_c_blockers,
        "known_non_blocking_backlog": known_non_blocking_backlog,
        "preferred_next_step": preferred_next_step,
    }


def _obvious_false_positive_in_top5(
    bundle: dict[str, Any],
    *,
    expected_template_roles: list[str],
    expected_pattern_ids: list[str],
) -> bool:
    subflow_templates = bundle.get("subflow_templates", []) or []
    if expected_template_roles and subflow_templates:
        top_template = subflow_templates[0] if isinstance(subflow_templates[0], dict) else {}
        if top_template and not _match_template(top_template, expected_template_roles) and _template_hit(
            bundle, expected_template_roles, 5
        ):
            return True

    system_patterns = bundle.get("system_patterns", []) or []
    if expected_pattern_ids and system_patterns:
        top_pattern = system_patterns[0] if isinstance(system_patterns[0], dict) else {}
        if top_pattern and _as_string(top_pattern.get("pattern_id")) not in expected_pattern_ids and _pattern_hit(
            bundle, expected_pattern_ids, 3
        ):
            return True
    return False


def _diagnose_retrieval(
    *,
    default_bundle: dict[str, Any],
    variant_bundle: dict[str, Any],
    expected_template_roles: list[str],
    expected_pattern_ids: list[str],
    template_assets_exist: bool,
    pattern_assets_exist: bool,
) -> str:
    if not expected_template_roles and not expected_pattern_ids:
        return "metadata_insufficient"

    if (expected_template_roles and not template_assets_exist) or (expected_pattern_ids and not pattern_assets_exist):
        return "asset_gap"

    default_template_hit_top5 = _template_hit(default_bundle, expected_template_roles, 5)
    default_pattern_hit_top3 = _pattern_hit(default_bundle, expected_pattern_ids, 3)
    variant_template_hit_top5 = _template_hit(variant_bundle, expected_template_roles, 5)
    variant_pattern_hit_top3 = _pattern_hit(variant_bundle, expected_pattern_ids, 3)
    false_positive = _obvious_false_positive_in_top5(
        default_bundle,
        expected_template_roles=expected_template_roles,
        expected_pattern_ids=expected_pattern_ids,
    )

    if (not default_template_hit_top5 and variant_template_hit_top5) or (
        not default_pattern_hit_top3 and variant_pattern_hit_top3
    ):
        return "query_coverage_gap"

    if default_template_hit_top5 or default_pattern_hit_top3:
        if false_positive or (
            default_template_hit_top5 and not _template_hit(default_bundle, expected_template_roles, 3)
        ) or (
            default_pattern_hit_top3 and not _pattern_hit(default_bundle, expected_pattern_ids, 1)
        ):
            return "ranking_issue"
        return "healthy"

    return "ranking_issue"


def _meets_case_expectation(
    *,
    diagnosis: str,
    default_bundle: dict[str, Any],
    expected_template_roles: list[str],
    expected_pattern_ids: list[str],
    template_assets_exist: bool,
    pattern_assets_exist: bool,
) -> bool:
    if diagnosis == "metadata_insufficient":
        return False
    if (expected_template_roles and not template_assets_exist) or (expected_pattern_ids and not pattern_assets_exist):
        return diagnosis == "asset_gap"
    template_ok = True if not expected_template_roles else _template_hit(default_bundle, expected_template_roles, 5)
    pattern_ok = True if not expected_pattern_ids else _pattern_hit(default_bundle, expected_pattern_ids, 3)
    return template_ok and pattern_ok


def _build_case_result(
    case: Phase6RealQueryCase,
    *,
    default_bundle: dict[str, Any],
    variant_bundle: dict[str, Any],
    expected_template_roles: list[str],
    expected_pattern_ids: list[str],
    missing_template_roles: list[str],
    missing_pattern_ids: list[str],
    template_assets_exist: bool,
    pattern_assets_exist: bool,
    exception: Exception | None,
) -> dict[str, Any]:
    diagnosis = "metadata_insufficient"
    if exception is None:
        diagnosis = _diagnose_retrieval(
            default_bundle=default_bundle,
            variant_bundle=variant_bundle,
            expected_template_roles=expected_template_roles,
            expected_pattern_ids=expected_pattern_ids,
            template_assets_exist=template_assets_exist,
            pattern_assets_exist=pattern_assets_exist,
        )

    case_result = {
        "case_id": case.case_id,
        "query": case.query,
        "case_type": case.case_type,
        "expected_template_roles": expected_template_roles,
        "expected_pattern_ids": expected_pattern_ids,
        "target_template_hit_top1": _template_hit(default_bundle, expected_template_roles, 1),
        "target_template_hit_top3": _template_hit(default_bundle, expected_template_roles, 3),
        "target_template_hit_top5": _template_hit(default_bundle, expected_template_roles, 5),
        "target_pattern_hit_top1": _pattern_hit(default_bundle, expected_pattern_ids, 1),
        "target_pattern_hit_top3": _pattern_hit(default_bundle, expected_pattern_ids, 3),
        "obvious_false_positive_in_top5": _obvious_false_positive_in_top5(
            default_bundle,
            expected_template_roles=expected_template_roles,
            expected_pattern_ids=expected_pattern_ids,
        ),
        "retrieval_diagnosis": diagnosis,
        "template_assets_exist": template_assets_exist,
        "pattern_assets_exist": pattern_assets_exist,
        "missing_template_roles": list(missing_template_roles),
        "missing_pattern_ids": list(missing_pattern_ids),
        "asset_gap_reason": _asset_gap_reason(
            missing_template_roles=missing_template_roles,
            missing_pattern_ids=missing_pattern_ids,
        ),
        "default_top_subflow_template_ids": _bundle_top_ids(
            default_bundle, "top_subflow_template_ids", "subflow_templates"
        ),
        "default_top_system_pattern_ids": _bundle_top_ids(
            default_bundle, "top_system_pattern_ids", "system_patterns"
        ),
        "default_top_subflow_template_roles": _template_roles(default_bundle),
        "default_top_subflow_scores": list(
            ((default_bundle.get("metadata", {}) or {}).get("top_subflow_scores", []) or [])
        ),
        "default_top_system_pattern_scores": list(
            ((default_bundle.get("metadata", {}) or {}).get("top_system_pattern_scores", []) or [])
        ),
        "variant_top_subflow_template_ids": _bundle_top_ids(
            variant_bundle, "top_subflow_template_ids", "subflow_templates"
        ),
        "variant_top_system_pattern_ids": _bundle_top_ids(
            variant_bundle, "top_system_pattern_ids", "system_patterns"
        ),
        "default_query_variants": list(((default_bundle.get("metadata", {}) or {}).get("query_variants", []) or [])),
        "variant_query_variants": list(((variant_bundle.get("metadata", {}) or {}).get("query_variants", []) or [])),
        "variant_improved_template_hit_top5": (
            not _template_hit(default_bundle, expected_template_roles, 5)
            and _template_hit(variant_bundle, expected_template_roles, 5)
        ),
        "variant_improved_pattern_hit_top3": (
            not _pattern_hit(default_bundle, expected_pattern_ids, 3)
            and _pattern_hit(variant_bundle, expected_pattern_ids, 3)
        ),
        "meets_expectation": False,
        "error_type": type(exception).__name__ if exception is not None else "",
        "error_message": str(exception) if exception is not None else "",
    }
    case_result["meets_expectation"] = _meets_case_expectation(
        diagnosis=diagnosis,
        default_bundle=default_bundle,
        expected_template_roles=expected_template_roles,
        expected_pattern_ids=expected_pattern_ids,
        template_assets_exist=template_assets_exist,
        pattern_assets_exist=pattern_assets_exist,
    )
    return case_result


def _write_eval_markdown(run_dir: Path, summary: dict[str, Any]) -> Path:
    lines = [
        "# Phase 6 Retrieval Eval",
        "",
        f"- 生成时间：{summary['generated_at']}",
        f"- case_count：{summary['case_count']}",
        f"- healthy_count：{summary['diagnosis_counts']['healthy']}",
        f"- asset_gap_count：{summary['diagnosis_counts']['asset_gap']}",
        f"- query_coverage_gap_count：{summary['diagnosis_counts']['query_coverage_gap']}",
        f"- ranking_issue_count：{summary['diagnosis_counts']['ranking_issue']}",
        f"- metadata_insufficient_count：{summary['diagnosis_counts']['metadata_insufficient']}",
        f"- golden_template_hit_rate_top5：`{summary['golden_template_hit_rate_top5']}`",
        f"- golden_pattern_hit_rate_top3：`{summary['golden_pattern_hit_rate_top3']}`",
        f"- all_passed：`{summary['all_passed']}`",
        f"- ready_for_c：`{summary['ready_for_c']}`",
        f"- ready_for_c_reason：`{summary['ready_for_c_reason']}`",
        f"- preferred_next_step：`{summary['preferred_next_step']}`",
        f"- run_dir：`{summary['run_dir']}`",
        "",
        "## Diagnosis Case IDs",
        "",
    ]
    for diagnosis, case_ids in (summary.get("diagnosis_case_ids", {}) or {}).items():
        lines.append(f"- {diagnosis}: `{', '.join(case_ids) if case_ids else 'none'}`")

    lines.extend([
        "",
        f"- template_asset_gap_case_ids：`{', '.join(summary['template_asset_gap_case_ids']) if summary['template_asset_gap_case_ids'] else 'none'}`",
        f"- pattern_asset_gap_case_ids：`{', '.join(summary['pattern_asset_gap_case_ids']) if summary['pattern_asset_gap_case_ids'] else 'none'}`",
        "",
        "## Asset Gap Aggregates",
        "",
        f"- asset_gap_template_role_counts：`{json.dumps(summary['asset_gap_template_role_counts'], ensure_ascii=False, sort_keys=True)}`",
        f"- asset_gap_pattern_id_counts：`{json.dumps(summary['asset_gap_pattern_id_counts'], ensure_ascii=False, sort_keys=True)}`",
        f"- asset_gap_case_type_counts：`{json.dumps(summary['asset_gap_case_type_counts'], ensure_ascii=False, sort_keys=True)}`",
        f"- single_root_asset_gap：`{json.dumps(summary['single_root_asset_gap'], ensure_ascii=False, sort_keys=True)}`",
        f"- ready_for_c_blockers：`{', '.join(summary['ready_for_c_blockers']) if summary['ready_for_c_blockers'] else 'none'}`",
        "",
        "## Asset Gap Role Diagnostics",
        "",
    ])
    for template_role, diagnostic in (summary.get("asset_gap_template_role_diagnostics", {}) or {}).items():
        lines.append(
            f"- {template_role}: "
            f"`root={diagnostic.get('likely_gap_stage', 'unknown')}; "
            f"pattern_pages={','.join(diagnostic.get('source_pattern_page_keys', [])) or 'none'}; "
            f"flows={','.join(diagnostic.get('source_flow_paths', [])) or 'none'}; "
            f"subflows={','.join(diagnostic.get('matched_subflow_names', [])) or 'none'}; "
            f"adjacent_subflows={','.join(diagnostic.get('adjacent_subflow_definition_names', [])) or 'none'}; "
            f"objects={','.join(diagnostic.get('matched_object_names', [])) or 'none'}`"
        )

    lines.extend([
        "",
        "## Case Results",
        "",
    ])
    for item in summary["results"]:
        lines.extend(
            [
                f"### {item['case_id']}",
                f"- case_type: `{item['case_type']}`",
                f"- query: `{item['query']}`",
                f"- retrieval_diagnosis: `{item['retrieval_diagnosis']}`",
                f"- meets_expectation: `{item['meets_expectation']}`",
                f"- target_template_hit_top1/top3/top5: `{item['target_template_hit_top1']}` / `{item['target_template_hit_top3']}` / `{item['target_template_hit_top5']}`",
                f"- target_pattern_hit_top1/top3: `{item['target_pattern_hit_top1']}` / `{item['target_pattern_hit_top3']}`",
                f"- obvious_false_positive_in_top5: `{item['obvious_false_positive_in_top5']}`",
                f"- asset_gap_reason: `{item['asset_gap_reason'] or 'none'}`",
                f"- asset_gap_root_cause: `{item['asset_gap_root_cause'] or 'none'}`",
                f"- default_top_subflow_template_ids: `{', '.join(item['default_top_subflow_template_ids']) if item['default_top_subflow_template_ids'] else 'none'}`",
                f"- default_top_system_pattern_ids: `{', '.join(item['default_top_system_pattern_ids']) if item['default_top_system_pattern_ids'] else 'none'}`",
                f"- variant_top_subflow_template_ids: `{', '.join(item['variant_top_subflow_template_ids']) if item['variant_top_subflow_template_ids'] else 'none'}`",
                f"- variant_top_system_pattern_ids: `{', '.join(item['variant_top_system_pattern_ids']) if item['variant_top_system_pattern_ids'] else 'none'}`",
            ]
        )
        if item["missing_template_roles"]:
            lines.append(f"- missing_template_roles: `{', '.join(item['missing_template_roles'])}`")
        if item["missing_pattern_ids"]:
            lines.append(f"- missing_pattern_ids: `{', '.join(item['missing_pattern_ids'])}`")
        if item["asset_gap_source_pattern_page_keys"]:
            lines.append(
                f"- asset_gap_source_pattern_page_keys: `{', '.join(item['asset_gap_source_pattern_page_keys'])}`"
            )
        if item["asset_gap_source_flow_paths"]:
            lines.append(f"- asset_gap_source_flow_paths: `{', '.join(item['asset_gap_source_flow_paths'])}`")
        if item["error_type"] or item["error_message"]:
            lines.append(f"- error: `{item['error_type']}: {item['error_message']}`")
        lines.append("")

    summary_md = run_dir / "phase6_retrieval_eval_summary.md"
    write_text(summary_md, "\n".join(lines))
    return summary_md


def run_eval(
    *,
    case_file_path: str | Path | None = None,
    output_root: str | Path | None = None,
    bundle_runner: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload, cases = load_phase6_cases(case_file_path=case_file_path)
    templates, patterns, _manifest = load_pattern_library_assets()
    available_template_roles = {_as_string(item.get("template_role")) for item in templates if _as_string(item.get("template_role"))}
    available_pattern_ids = {_as_string(item.get("pattern_id")) for item in patterns if _as_string(item.get("pattern_id"))}

    if bundle_runner is None:
        agent = RetrievalAgent()

        def bundle_runner(query: str, analysis_result: dict[str, Any]) -> dict[str, Any]:
            return agent.retrieve_bundle(query, analysis_result=analysis_result)

    output_root_path = Path(output_root) if output_root is not None else RETRIEVAL_EVAL_OUTPUT_ROOT
    run_dir = output_root_path / f"eval_{timestamp_token()}"
    run_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for case in cases:
        expected_template_roles = resolve_template_roles(case)
        expected_pattern_ids = list(case.expected_pattern_ids) or default_pattern_ids(patterns)
        missing_template_roles = _missing_expected_items(available_template_roles, expected_template_roles)
        missing_pattern_ids = _missing_expected_items(available_pattern_ids, expected_pattern_ids)
        template_assets_exist = _template_exists(available_template_roles, expected_template_roles)
        pattern_assets_exist = _pattern_exists(available_pattern_ids, expected_pattern_ids)

        default_bundle: dict[str, Any] = {}
        variant_bundle: dict[str, Any] = {}
        exception: Exception | None = None
        try:
            default_bundle = bundle_runner(
                case.query,
                build_retrieval_analysis_result(case, query_variants=[case.query]),
            )
            variant_bundle = bundle_runner(
                case.query,
                build_retrieval_analysis_result(
                    case,
                    query_variants=list(case.query_variants) or [case.query],
                ),
            )
        except Exception as exc:  # pragma: no cover - contract tests use stubs
            exception = exc

        results.append(
            _build_case_result(
                case,
                default_bundle=default_bundle,
                variant_bundle=variant_bundle,
                expected_template_roles=expected_template_roles,
                expected_pattern_ids=expected_pattern_ids,
                missing_template_roles=missing_template_roles,
                missing_pattern_ids=missing_pattern_ids,
                template_assets_exist=template_assets_exist,
                pattern_assets_exist=pattern_assets_exist,
                exception=exception,
            )
        )

    golden_results = [item for item in results if item["case_type"] == "golden_success"]
    diagnosis_counts = {
        diagnosis: sum(1 for item in results if item["retrieval_diagnosis"] == diagnosis)
        for diagnosis in ("healthy", "asset_gap", "query_coverage_gap", "ranking_issue", "metadata_insufficient")
    }
    diagnosis_case_ids = {
        diagnosis: [item["case_id"] for item in results if item["retrieval_diagnosis"] == diagnosis]
        for diagnosis in ("healthy", "asset_gap", "query_coverage_gap", "ranking_issue", "metadata_insufficient")
    }
    golden_template_hit_rate_top5 = round(
        sum(1 for item in golden_results if item["target_template_hit_top5"]) / len(golden_results),
        4,
    ) if golden_results else 0.0
    golden_pattern_hit_rate_top3 = round(
        sum(1 for item in golden_results if item["target_pattern_hit_top3"]) / len(golden_results),
        4,
    ) if golden_results else 0.0
    asset_gap_fields = _aggregate_asset_gap_fields(
        results,
        diagnosis_counts=diagnosis_counts,
        golden_results=golden_results,
    )

    summary_json_path = run_dir / "phase6_retrieval_eval_summary.json"
    summary_md_path = run_dir / "phase6_retrieval_eval_summary.md"
    summary = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "schema_version": str(payload.get("schema_version", "")),
        "case_owner": str(payload.get("case_owner", "")),
        "case_file": str((Path(case_file_path) if case_file_path is not None else CASE_FILE_PATH).resolve()),
        "case_count": len(results),
        "meets_expectation_count": sum(1 for item in results if item["meets_expectation"]),
        "diagnosis_counts": diagnosis_counts,
        "diagnosis_case_ids": diagnosis_case_ids,
        "template_asset_gap_case_ids": [item["case_id"] for item in results if item["missing_template_roles"]],
        "pattern_asset_gap_case_ids": [item["case_id"] for item in results if item["missing_pattern_ids"]],
        "golden_case_count": len(golden_results),
        "golden_template_hit_rate_top5": golden_template_hit_rate_top5,
        "golden_pattern_hit_rate_top3": golden_pattern_hit_rate_top3,
        "run_dir": str(run_dir.resolve()),
        "summary_json": str(summary_json_path.resolve()),
        "summary_md": str(summary_md_path.resolve()),
        "results": results,
    }
    summary.update(asset_gap_fields)
    summary["all_passed"] = bool(
        golden_template_hit_rate_top5 >= 0.9
        and golden_pattern_hit_rate_top3 >= 0.8
        and diagnosis_counts["metadata_insufficient"] == 0
    )

    marker_path = output_root_path / "_retained" / ("latest_green_run.json" if summary["all_passed"] else "latest_failure_run.json")
    summary["retention"] = {
        "run_marker": str(
            update_marker(
                marker_path,
                {
                    "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "run_dir": summary["run_dir"],
                    "all_passed": summary["all_passed"],
                    "case_count": summary["case_count"],
                },
            ).resolve()
        )
    }

    write_json(summary_json_path, summary)
    _write_eval_markdown(run_dir, summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Phase 6 retrieval evaluation.")
    parser.add_argument("--case-file", default=str(CASE_FILE_PATH), help="Phase 6 case file path.")
    parser.add_argument(
        "--output-root",
        default=str(RETRIEVAL_EVAL_OUTPUT_ROOT),
        help="Directory used to write phase6 retrieval eval outputs.",
    )
    args = parser.parse_args(argv)

    summary = run_eval(case_file_path=args.case_file, output_root=args.output_root)
    print(f"Phase 6 retrieval eval summary written to: {summary['summary_md']}")
    for item in summary["results"]:
        print(
            json.dumps(
                {
                    "case_id": item["case_id"],
                    "retrieval_diagnosis": item["retrieval_diagnosis"],
                    "target_template_hit_top5": item["target_template_hit_top5"],
                    "target_pattern_hit_top3": item["target_pattern_hit_top3"],
                },
                ensure_ascii=False,
            )
        )
    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
