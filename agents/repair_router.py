"""Rule-first repair routing for the Phase 4 repair loop."""
from __future__ import annotations

from typing import Any, Dict, List

from utils.phase3_contracts import (
    DEFAULT_RETRY_BUDGET,
    RouteDecision,
    default_retry_budget,
    default_retry_counts_by_scope,
)


REPAIR_DECISION_BY_SCOPE = {
    "planning": "planning_repair",
    "assembly": "assembly_repair",
    "compile": "compile_repair",
}
REPAIR_REASON_BY_DECISION = {
    "accept": "verification_passed",
    "planning_repair": "planning_retry_allowed",
    "assembly_repair": "assembly_retry_allowed",
    "compile_repair": "compile_retry_allowed",
    "reject_invalid_scope": "unsupported_repair_scope",
    "reject_budget_exhausted": "retry_budget_exhausted",
}
ROUTE_NEXT_NODE_BY_DECISION = {
    "accept": "END",
    "planning_repair": "repair_agent",
    "assembly_repair": "repair_agent",
    "compile_repair": "repair_agent",
    "reject": "END",
}


def _coerce_non_negative_int(value: Any, default: int = 0) -> int:
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return default


def _normalize_retry_budget(retry_budget: Dict[str, Any] | None) -> Dict[str, int]:
    normalized = default_retry_budget()
    for scope, default_value in DEFAULT_RETRY_BUDGET.items():
        if retry_budget is None:
            normalized[scope] = default_value
            continue
        normalized[scope] = _coerce_non_negative_int(retry_budget.get(scope), default_value)
    return normalized


def _normalize_retry_counts_by_scope(retry_counts_by_scope: Dict[str, Any] | None) -> Dict[str, int]:
    normalized = default_retry_counts_by_scope()
    for scope in normalized:
        if retry_counts_by_scope is None:
            normalized[scope] = 0
            continue
        normalized[scope] = _coerce_non_negative_int(retry_counts_by_scope.get(scope), 0)
    return normalized


def _collect_issue_ids(verification_report: Dict[str, Any]) -> List[str]:
    issue_ids: List[str] = []
    for issue in verification_report.get("issues", []) or []:
        issue_id = str((issue or {}).get("issue_id", "")).strip()
        if issue_id:
            issue_ids.append(issue_id)
    return issue_ids


class RepairRouter:
    """Convert verification output into a stable route decision."""

    def route(
        self,
        verification_report: Dict[str, Any],
        retry_budget: Dict[str, Any] | None = None,
        retry_counts_by_scope: Dict[str, Any] | None = None,
    ) -> RouteDecision:
        report = verification_report or {}
        normalized_budget = _normalize_retry_budget(retry_budget)
        normalized_counts = _normalize_retry_counts_by_scope(retry_counts_by_scope)

        status = str(report.get("status", "")).strip()
        repair_scope = str(report.get("repair_scope", "")).strip()
        issue_ids = _collect_issue_ids(report)
        retry_count_for_scope = normalized_counts.get(repair_scope, 0)
        retry_budget_for_scope = normalized_budget.get(repair_scope, 0)

        if status == "passed":
            decision = "accept"
            reason = REPAIR_REASON_BY_DECISION["accept"]
            retry_exhausted = False
        elif repair_scope not in REPAIR_DECISION_BY_SCOPE:
            decision = "reject"
            reason = REPAIR_REASON_BY_DECISION["reject_invalid_scope"]
            retry_exhausted = False
        elif retry_count_for_scope >= retry_budget_for_scope:
            decision = "reject"
            reason = REPAIR_REASON_BY_DECISION["reject_budget_exhausted"]
            retry_exhausted = True
        else:
            decision = REPAIR_DECISION_BY_SCOPE[repair_scope]
            reason = REPAIR_REASON_BY_DECISION[decision]
            retry_exhausted = False

        return {
            "decision": decision,
            "repair_scope": repair_scope,
            "next_node": ROUTE_NEXT_NODE_BY_DECISION[decision],
            "reason": reason,
            "issue_ids": issue_ids,
            "retry_exhausted": retry_exhausted,
            "retry_count_for_scope": retry_count_for_scope,
            "retry_budget_for_scope": retry_budget_for_scope,
        }

    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        retry_budget = _normalize_retry_budget(state.get("retry_budget"))
        retry_counts_by_scope = _normalize_retry_counts_by_scope(state.get("retry_counts_by_scope"))
        route_decision = self.route(
            state.get("verification_report", {}) or {},
            retry_budget=retry_budget,
            retry_counts_by_scope=retry_counts_by_scope,
        )

        state["retry_budget"] = retry_budget
        state["retry_counts_by_scope"] = retry_counts_by_scope
        state["retry_count"] = sum(retry_counts_by_scope.values())
        state["route_decision"] = route_decision
        if route_decision["decision"] != "accept":
            state["current_step"] = "repair_router_completed"
        return state
