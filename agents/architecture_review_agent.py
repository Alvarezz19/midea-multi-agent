"""Prepare and optionally pause at the architecture review stage."""
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


def _join_or_none(values: list[str], *, limit: int = 6) -> str:
    cleaned = [str(value or "").strip() for value in values if str(value or "").strip()]
    if not cleaned:
        return "无"
    head = cleaned[:limit]
    suffix = "" if len(cleaned) <= limit else f" 等 {len(cleaned)} 项"
    return "、".join(head) + suffix


class ArchitectureReviewAgent:
    """Freeze a user-readable architecture summary before subsystem planning."""

    @staticmethod
    def _build_review_request(state: dict[str, Any], review_id: str) -> dict[str, Any]:
        architecture_plan = state.get("architecture_plan", {}) or {}
        decomposition_result = state.get("decomposition_result", {}) or {}

        page_labels = [
            str(page.get("label", "") or page.get("page_id", "") or "").strip()
            for page in architecture_plan.get("pages", []) or []
            if isinstance(page, dict)
        ]
        subsystem_labels = [
            str(slot.get("subsystem_id", "") or "").strip()
            for slot in architecture_plan.get("subsystem_slots", []) or []
            if isinstance(slot, dict)
        ]
        if not subsystem_labels:
            subsystem_labels = [
                str(item.get("subsystem_id", "") or "").strip()
                for item in decomposition_result.get("subsystem_descriptors", []) or []
                if isinstance(item, dict)
            ]

        shared_signal_lines: list[str] = []
        for entry in (architecture_plan.get("shared_signal_registry", []) or [])[:5]:
            if not isinstance(entry, dict):
                continue
            signal_name = str(
                entry.get("signal_name", "")
                or entry.get("canonical_signal_key", "")
                or entry.get("signal_key", "")
                or ""
            ).strip()
            owner = str(entry.get("owner_subsystem_id", "") or "").strip() or "待定"
            consumers = _join_or_none(list(entry.get("consumers", []) or []), limit=3)
            if signal_name:
                shared_signal_lines.append(f"- {signal_name}: owner={owner}; consumers={consumers}")

        global_constraints = [
            str(item.get("summary", "") or item.get("rule", "") or item).strip()
            for item in architecture_plan.get("global_constraints", []) or []
            if str(item).strip()
        ]

        context_lines = [
            f"页面列表：{_join_or_none(page_labels)}",
            f"子系统列表：{_join_or_none(subsystem_labels)}",
            "共享信号摘要：",
        ]
        if shared_signal_lines:
            context_lines.extend(shared_signal_lines)
        else:
            context_lines.append("- 无")
        context_lines.append(f"关键全局约束：{_join_or_none(global_constraints, limit=4)}")

        return {
            "review_id": review_id,
            "stage": "architecture_review",
            "question": "请确认当前系统骨架是否可继续进入子系统规划；若需调整，请只反馈需求或约束层修改意见。",
            "options": [
                {"label": "批准继续", "value": "approve", "description": "接受当前骨架并继续子系统规划。"},
                {"label": "反馈后重规划", "value": "feedback", "description": "补充结构约束并重跑 architecture_planning。"},
                {"label": "补充约束", "value": "clarify", "description": "补充需求信息后重跑 architecture_planning。"},
                {"label": "终止本轮", "value": "reject", "description": "结束当前工作流。"},
            ],
            "context_summary": "\n".join(context_lines),
            "created_at": utc_now_iso(),
        }

    def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        architecture_plan = state.get("architecture_plan", {}) or {}
        decomposition_result = state.get("decomposition_result", {}) or {}
        state["review_enabled"] = bool(state.get("enable_hitl_architecture_review", False))

        if not architecture_plan and not decomposition_result:
            state["review_required"] = False
            state["review_enabled"] = False
            state["hitl_stage"] = "none"
            state["review_status"] = "not_required"
            state["current_step"] = "architecture_review_skipped"
            return state

        review_id = str(state.get("review_id", "") or "").strip()
        request = state.get("review_request", {})
        same_stage_request = (
            isinstance(request, dict)
            and str(request.get("stage", "")).strip() == "architecture_review"
            and str(request.get("review_id", "")).strip() == review_id
        )
        if not review_id or not same_stage_request:
            review_id = make_review_id("architecture_review", list(state.get("review_history", []) or []))
            request = self._build_review_request(state, review_id)
            state["review_request"] = request
            state["review_response"] = empty_review_response()
            state["review_id"] = review_id
            state["review_required"] = True
            state["hitl_stage"] = "architecture_review"
            state["review_status"] = "pending"
            state["review_history"] = upsert_review_history_entry(
                list(state.get("review_history", []) or []),
                stage="architecture_review",
                review_id=review_id,
                status="pending",
                request=request,
            )
            if not bool(state.get("review_enabled", False)):
                state["review_status"] = "assumed"
                state["current_step"] = "architecture_review_assumed"
                state["review_history"] = upsert_review_history_entry(
                    list(state.get("review_history", []) or []),
                    stage="architecture_review",
                    review_id=review_id,
                    status="assumed",
                    request=request,
                )
            else:
                state["current_step"] = "architecture_review_prepared"
            return state

        state["review_required"] = True
        state["hitl_stage"] = "architecture_review"

        if not bool(state.get("review_enabled", False)):
            state["review_status"] = "assumed"
            state["current_step"] = "architecture_review_assumed"
            state["review_history"] = upsert_review_history_entry(
                list(state.get("review_history", []) or []),
                stage="architecture_review",
                review_id=review_id,
                status="assumed",
                request=request,
            )
            return state

        response = normalize_review_response(interrupt(request), review_id=review_id)
        state["review_response"] = response
        state["review_status"] = "answered"
        state["current_step"] = "architecture_review_answered"
        state["review_history"] = upsert_review_history_entry(
            list(state.get("review_history", []) or []),
            stage="architecture_review",
            review_id=review_id,
            status="answered",
            request=request,
            response=response,
        )
        return state
