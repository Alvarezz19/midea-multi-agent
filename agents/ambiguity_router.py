"""Route early clarification only when the requirement ambiguity is material."""
from __future__ import annotations

from typing import Any

from agents.analysis_agent import derive_clarification_signals


class AmbiguityRouter:
    """Inspect analysis/requirement outputs and decide whether clarification is required."""

    def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        analysis_result = state.get("analysis_result", {})
        requirement_spec = state.get("requirement_spec", {})

        clarification_signals = (
            (analysis_result or {}).get("clarification_signals", {})
            if isinstance(analysis_result, dict)
            else {}
        )
        if not isinstance(clarification_signals, dict) or not clarification_signals:
            clarification_signals = derive_clarification_signals(analysis_result, requirement_spec)
            analysis_result = dict(analysis_result or {})
            analysis_result["clarification_signals"] = clarification_signals
            state["analysis_result"] = analysis_result

        review_required = bool(clarification_signals.get("should_clarify", False))
        state["review_required"] = review_required
        state["hitl_stage"] = "clarification_review" if review_required else "none"
        state["review_status"] = "pending" if review_required else "not_required"
        state["current_step"] = "ambiguity_routed"
        return state
