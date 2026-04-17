from __future__ import annotations

from typing import Any


FAILURE_BUCKETS = {
    "passed",
    "repair_then_passed",
    "ambiguous_shared_signal",
    "retry_budget_exhausted",
    "template_interface_mismatch",
    "missing_placeholder_source",
    "retrieval_asset_gap",
    "retrieval_ranking_issue",
    "other_retryable_error",
    "unexpected_exception",
}

END_STATES = {
    "passed",
    "passed_after_repair",
    "rejected_ambiguous_shared_signal",
    "rejected_budget_exhausted",
    "rejected_template_interface_mismatch",
    "rejected_missing_placeholder_source",
    "rejected_retrieval_asset_gap",
    "rejected_retrieval_ranking_issue",
    "rejected_other_retryable_error",
    "unexpected_exception",
}

_RULE_ID_FAILURE_BUCKETS = {
    "template_input_interface_mismatch": "template_interface_mismatch",
    "template_output_interface_mismatch": "template_interface_mismatch",
    "template_interface_mismatch": "template_interface_mismatch",
    "missing_placeholder_source": "missing_placeholder_source",
}

_UNRESOLVED_TYPE_FAILURE_BUCKETS = {
    "ambiguous_shared_signal": "ambiguous_shared_signal",
    "template_input_interface_mismatch": "template_interface_mismatch",
    "template_output_interface_mismatch": "template_interface_mismatch",
    "template_interface_mismatch": "template_interface_mismatch",
    "missing_placeholder_source": "missing_placeholder_source",
}

_REPAIR_REJECT_CATEGORY_FAILURE_BUCKETS = {
    "ambiguous_shared_signal": "ambiguous_shared_signal",
    "budget_exhausted": "retry_budget_exhausted",
    "unsupported_repair_issue": "other_retryable_error",
    "unsupported_repair_scope": "other_retryable_error",
    "no_repairable_issue": "other_retryable_error",
    "repair_patch_failed": "other_retryable_error",
}

_ROUTE_REASON_FAILURE_BUCKETS = {
    "ambiguous_shared_signal_unresolved": "ambiguous_shared_signal",
    "retry_budget_exhausted": "retry_budget_exhausted",
    "unsupported_repair_issue": "other_retryable_error",
    "unsupported_repair_scope": "other_retryable_error",
    "no_repairable_issue": "other_retryable_error",
    "repair_patch_failed": "other_retryable_error",
}

_END_STATE_BY_FAILURE_BUCKET = {
    "ambiguous_shared_signal": "rejected_ambiguous_shared_signal",
    "retry_budget_exhausted": "rejected_budget_exhausted",
    "template_interface_mismatch": "rejected_template_interface_mismatch",
    "missing_placeholder_source": "rejected_missing_placeholder_source",
    "retrieval_asset_gap": "rejected_retrieval_asset_gap",
    "retrieval_ranking_issue": "rejected_retrieval_ranking_issue",
    "other_retryable_error": "rejected_other_retryable_error",
}


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _extract_rule_ids(verification_report: dict[str, Any] | None) -> list[str]:
    if not isinstance(verification_report, dict):
        return []

    rule_ids: list[str] = []
    top_level_rule_id = _normalize_text(verification_report.get("rule_id"))
    if top_level_rule_id:
        rule_ids.append(top_level_rule_id)

    for issue in verification_report.get("issues", []) or []:
        if not isinstance(issue, dict):
            continue
        rule_id = _normalize_text(issue.get("rule_id"))
        if rule_id:
            rule_ids.append(rule_id)

    return rule_ids


def _bucket_from_rule_ids(rule_ids: list[str]) -> str:
    for rule_id in rule_ids:
        bucket = _RULE_ID_FAILURE_BUCKETS.get(_normalize_text(rule_id))
        if bucket:
            return bucket
    return ""


def _bucket_from_unresolved_types(unresolved_item_types: list[str] | None) -> str:
    for unresolved_type in unresolved_item_types or []:
        bucket = _UNRESOLVED_TYPE_FAILURE_BUCKETS.get(_normalize_text(unresolved_type))
        if bucket:
            return bucket
    return ""


def ordered_subsystem_ids(
    architecture_plan: dict[str, Any] | None,
    subsystem_plan_map: dict[str, Any] | None,
) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()

    for slot in (architecture_plan or {}).get("subsystem_slots", []) or []:
        if not isinstance(slot, dict):
            continue
        subsystem_id = _normalize_text(slot.get("subsystem_id"))
        if subsystem_id and subsystem_id not in seen:
            ordered.append(subsystem_id)
            seen.add(subsystem_id)

    for subsystem_id in (subsystem_plan_map or {}).keys():
        normalized = _normalize_text(subsystem_id)
        if normalized and normalized not in seen:
            ordered.append(normalized)
            seen.add(normalized)

    return ordered


def derive_failure_bucket(
    *,
    verification_report: dict[str, Any] | None = None,
    route_decision: dict[str, Any] | None = None,
    repair_history: list[dict[str, Any]] | None = None,
    unresolved_item_types: list[str] | None = None,
    repair_reject_category: str = "",
    workflow_status: str = "",
    error_type: str = "",
    error_message: str = "",
) -> str:
    if _normalize_text(error_type) or _normalize_text(error_message) or _normalize_text(workflow_status) == "failed":
        return "unexpected_exception"

    normalized_repair_category = _normalize_text(repair_reject_category)
    if normalized_repair_category:
        return _REPAIR_REJECT_CATEGORY_FAILURE_BUCKETS.get(normalized_repair_category, "other_retryable_error")

    route_decision = route_decision or {}
    if _normalize_text(route_decision.get("decision")) == "reject":
        reject_bucket = _ROUTE_REASON_FAILURE_BUCKETS.get(_normalize_text(route_decision.get("reason")))
        if reject_bucket:
            return reject_bucket

    rule_bucket = _bucket_from_rule_ids(_extract_rule_ids(verification_report))
    if rule_bucket:
        return rule_bucket

    unresolved_bucket = _bucket_from_unresolved_types(unresolved_item_types)
    if unresolved_bucket:
        return unresolved_bucket

    verification_status = _normalize_text((verification_report or {}).get("status")).lower()
    if verification_status == "passed":
        return "repair_then_passed" if repair_history else "passed"

    if _normalize_text(route_decision.get("decision")) == "accept" and verification_status == "passed":
        return "repair_then_passed" if repair_history else "passed"

    return "other_retryable_error"


def derive_end_state(
    *,
    failure_bucket: str,
    route_decision: str = "",
    verification_status: str = "",
) -> str:
    normalized_bucket = _normalize_text(failure_bucket)
    if normalized_bucket == "unexpected_exception":
        return "unexpected_exception"
    if normalized_bucket == "passed":
        return "passed"
    if normalized_bucket == "repair_then_passed":
        return "passed_after_repair"
    if normalized_bucket in _END_STATE_BY_FAILURE_BUCKET:
        return _END_STATE_BY_FAILURE_BUCKET[normalized_bucket]

    if _normalize_text(verification_status).lower() == "passed":
        return "passed"
    if _normalize_text(route_decision) == "reject":
        return "rejected_other_retryable_error"
    return "rejected_other_retryable_error"
