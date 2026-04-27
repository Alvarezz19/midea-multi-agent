"""Apply clarification feedback back onto requirement-side inputs only."""
from __future__ import annotations

from typing import Any

from agents.analysis_agent import derive_clarification_signals
from utils.phase3_contracts import (
    CLARIFICATION_ALLOWED_REQUIREMENT_KEYS,
    merge_requirement_side_patch,
    normalize_review_response,
    upsert_review_history_entry,
)


def _append_unique_text(target: list[str], values: list[str]) -> list[str]:
    seen = {str(item or "").strip() for item in target if str(item or "").strip()}
    result = [str(item or "").strip() for item in target if str(item or "").strip()]
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result


class ClarificationApplyAgent:
    """Update only analysis/requirement inputs and then re-enter retrieval."""

    def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        response = normalize_review_response(
            state.get("review_response", {}),
            review_id=str(state.get("review_id", "") or "").strip(),
        )

        analysis_result = dict(state.get("analysis_result", {}) or {})
        scenario = dict(analysis_result.get("scenario_analysis", {}) or {})
        requirement_spec = merge_requirement_side_patch(
            state.get("requirement_spec", {}),
            response.get("updated_constraints", {}),
            allowed_keys=CLARIFICATION_ALLOWED_REQUIREMENT_KEYS,
        )

        note_lines = [str(answer).strip() for answer in response.get("answers", []) if str(answer).strip()]
        feedback = str(response.get("feedback", "") or "").strip()
        if feedback:
            note_lines.append(feedback)

        if note_lines:
            scenario["assumptions"] = _append_unique_text(list(scenario.get("assumptions", []) or []), note_lines)
            requirement_spec["assumptions"] = _append_unique_text(
                list(requirement_spec.get("assumptions", []) or []),
                note_lines,
            )

        analysis_result["scenario_analysis"] = scenario
        analysis_result["clarification_signals"] = derive_clarification_signals(analysis_result, requirement_spec)

        state["analysis_result"] = analysis_result
        state["requirement_spec"] = requirement_spec
        state["clarification_round"] = int(state.get("clarification_round", 0) or 0) + 1
        state["review_enabled"] = False
        state["review_status"] = "applied"
        state["hitl_stage"] = "none"
        state["current_step"] = "clarification_applied"

        if response.get("decision") == "reject":
            final_output = dict(state.get("final_output", {}) or {})
            final_output["review_abort"] = {
                "stage": "clarification_review",
                "review_id": response.get("review_id", ""),
                "reason": feedback or "clarification rejected by reviewer",
            }
            state["final_output"] = final_output
            state["review_enabled"] = False
            state["review_status"] = "rejected"

        state["review_history"] = upsert_review_history_entry(
            list(state.get("review_history", []) or []),
            stage="clarification_review",
            review_id=str(response.get("review_id", "") or "").strip(),
            status=str(state.get("review_status", "") or "applied").strip(),
            request=dict(state.get("review_request", {}) or {}),
            response=response,
        )
        return state
