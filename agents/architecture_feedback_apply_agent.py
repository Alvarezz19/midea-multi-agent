"""Apply architecture review feedback back onto requirement-side inputs only."""
from __future__ import annotations

from typing import Any

from utils.phase3_contracts import (
    ARCHITECTURE_FEEDBACK_ALLOWED_REQUIREMENT_KEYS,
    empty_review_request,
    empty_review_response,
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


class ArchitectureFeedbackApplyAgent:
    """Consume architecture review feedback and decide whether to re-plan or continue."""

    def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        review_id = str(state.get("review_id", "") or "").strip()
        review_request = dict(state.get("review_request", {}) or {})
        response = normalize_review_response(state.get("review_response", {}), review_id=review_id)
        decision = str(response.get("decision", "") or "").strip()

        if decision == "approve":
            state["review_enabled"] = False
            state["review_status"] = "applied"
            state["hitl_stage"] = "none"
            state["current_step"] = "architecture_feedback_approved"
            state["review_history"] = upsert_review_history_entry(
                list(state.get("review_history", []) or []),
                stage="architecture_review",
                review_id=review_id,
                status="applied",
                request=review_request,
                response=response,
            )
            return state

        if decision == "reject":
            final_output = dict(state.get("final_output", {}) or {})
            final_output["review_abort"] = {
                "stage": "architecture_review",
                "review_id": review_id,
                "reason": str(response.get("feedback", "") or "").strip() or "architecture review rejected",
            }
            state["final_output"] = final_output
            state["review_enabled"] = False
            state["review_status"] = "rejected"
            state["hitl_stage"] = "none"
            state["current_step"] = "architecture_feedback_rejected"
            state["review_history"] = upsert_review_history_entry(
                list(state.get("review_history", []) or []),
                stage="architecture_review",
                review_id=review_id,
                status="rejected",
                request=review_request,
                response=response,
            )
            return state

        requirement_spec = merge_requirement_side_patch(
            state.get("requirement_spec", {}),
            response.get("updated_constraints", {}),
            allowed_keys=ARCHITECTURE_FEEDBACK_ALLOWED_REQUIREMENT_KEYS,
        )

        notes = [str(answer).strip() for answer in response.get("answers", []) if str(answer).strip()]
        feedback = str(response.get("feedback", "") or "").strip()
        if feedback:
            notes.append(feedback)

        if notes:
            requirement_spec["assumptions"] = _append_unique_text(
                list(requirement_spec.get("assumptions", []) or []),
                notes,
            )

        state["requirement_spec"] = requirement_spec
        state["architecture_feedback_patch"] = {
            "review_id": review_id,
            "decision": decision,
            "answers": list(response.get("answers", []) or []),
            "feedback": feedback,
            "updated_constraints": dict(response.get("updated_constraints", {}) or {}),
        }
        state["review_id"] = ""
        state["review_request"] = empty_review_request()
        state["review_response"] = empty_review_response()
        state["review_enabled"] = False
        state["review_status"] = "applied"
        state["hitl_stage"] = "none"
        state["current_step"] = "architecture_feedback_applied"
        state["review_history"] = upsert_review_history_entry(
            list(state.get("review_history", []) or []),
            stage="architecture_review",
            review_id=review_id,
            status="applied",
            request=review_request,
            response=response,
        )
        return state
