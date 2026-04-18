"""Prepare and pause at the clarification review stage."""
from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from utils.phase3_contracts import (
    empty_review_response,
    make_review_id,
    normalize_review_response,
    upsert_review_history_entry,
    utc_now_iso,
)


class ClarificationReviewAgent:
    """Freeze the clarification request and optionally pause for HITL input."""

    @staticmethod
    def _build_review_request(state: dict[str, Any], review_id: str) -> dict[str, Any]:
        clarification_signals = (
            ((state.get("analysis_result", {}) or {}).get("clarification_signals", {}) or {}).get("signals", [])
        )
        bullets = []
        for signal in clarification_signals[:4]:
            if not isinstance(signal, dict):
                continue
            message = str(signal.get("message", "")).strip()
            if message:
                bullets.append(f"- {message}")

        requirement_spec = state.get("requirement_spec", {}) or {}
        scenario_summary = str(requirement_spec.get("scenario_summary", "") or "").strip()
        context_lines = []
        if scenario_summary:
            context_lines.append(f"场景摘要：{scenario_summary}")
        if bullets:
            context_lines.append("待澄清点：")
            context_lines.extend(bullets)
        if not context_lines:
            context_lines.append("需求存在高优先级歧义，需要补充关键约束。")

        return {
            "review_id": review_id,
            "stage": "clarification_review",
            "question": "请补充当前需求中缺失的关键约束，至少说明系统类型、核心子系统或必需页面。",
            "options": [
                {"label": "补充约束", "value": "clarify", "description": "提供补充信息并继续规划。"},
                {"label": "沿用保守假设", "value": "approve", "description": "接受当前保守假设继续。"},
                {"label": "反馈后继续", "value": "feedback", "description": "给出反馈意见并继续。"},
                {"label": "终止本轮", "value": "reject", "description": "结束当前工作流。"},
            ],
            "context_summary": "\n".join(context_lines),
            "created_at": utc_now_iso(),
        }

    def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        state["review_enabled"] = bool(state.get("enable_hitl_clarification", False))
        if not bool(state.get("review_required", False)):
            state["hitl_stage"] = "none"
            state["review_enabled"] = False
            state["review_status"] = "not_required"
            state["current_step"] = "clarification_skipped"
            return state

        review_id = str(state.get("review_id", "") or "").strip()
        if not review_id:
            review_id = make_review_id("clarification_review", list(state.get("review_history", []) or []))

        request = state.get("review_request", {})
        if not isinstance(request, dict) or str(request.get("review_id", "")).strip() != review_id:
            request = self._build_review_request(state, review_id)
            state["review_request"] = request
            state["review_response"] = empty_review_response()
            state["review_id"] = review_id
            state["hitl_stage"] = "clarification_review"
            state["review_status"] = "pending"
            state["review_history"] = upsert_review_history_entry(
                list(state.get("review_history", []) or []),
                stage="clarification_review",
                review_id=review_id,
                status="pending",
                request=request,
            )
            if not bool(state.get("review_enabled", False)):
                state["review_status"] = "assumed"
                state["review_history"] = upsert_review_history_entry(
                    list(state.get("review_history", []) or []),
                    stage="clarification_review",
                    review_id=review_id,
                    status="assumed",
                    request=request,
                )
                state["current_step"] = "clarification_review_assumed"
            else:
                state["current_step"] = "clarification_review_prepared"
            return state

        if not bool(state.get("review_enabled", False)):
            state["review_status"] = "assumed"
            state["current_step"] = "clarification_review_assumed"
            state["review_history"] = upsert_review_history_entry(
                list(state.get("review_history", []) or []),
                stage="clarification_review",
                review_id=review_id,
                status="assumed",
                request=request,
            )
            return state

        response = normalize_review_response(interrupt(request), review_id=review_id)
        state["review_response"] = response
        state["review_status"] = "answered"
        state["current_step"] = "clarification_review_answered"
        state["review_history"] = upsert_review_history_entry(
            list(state.get("review_history", []) or []),
            stage="clarification_review",
            review_id=review_id,
            status="answered",
            request=request,
            response=response,
        )
        return state
