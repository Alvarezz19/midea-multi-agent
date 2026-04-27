"""ArchitecturePlanner 的可选 LLM 架构建议增强器。"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field


class ArchitectureAdvice(BaseModel):
    """架构规划补丁建议。"""

    page_patch: List[Dict[str, Any]] = Field(default_factory=list)
    subsystem_patch: List[Dict[str, Any]] = Field(default_factory=list)
    template_preferences: Dict[str, List[str]] = Field(default_factory=dict)
    shared_signal_patch: List[Dict[str, Any]] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    confidence: float = 0.0


def _model_to_dict(model: Any) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    if hasattr(model, "dict"):
        return model.dict()
    return dict(model or {})


def _validate_payload(payload: Any) -> ArchitectureAdvice:
    if isinstance(payload, ArchitectureAdvice):
        return payload
    if hasattr(ArchitectureAdvice, "model_validate"):
        return ArchitectureAdvice.model_validate(payload)
    return ArchitectureAdvice.parse_obj(payload)


class ArchitectureAdvisor:
    """只输出受控架构补丁，不接管 deterministic planner。"""

    def __init__(self, llm: Any, provider: str = "", model: str = "") -> None:
        self.llm = llm
        self.provider = provider
        self.model = model
        self.prompt = self._create_prompt()

    @staticmethod
    def _extract_json_text(content: str) -> str:
        json_match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL | re.IGNORECASE)
        if json_match:
            return json_match.group(1).strip()
        obj_match = re.search(r"(\{.*\})", content, re.DOTALL)
        if obj_match:
            return obj_match.group(1).strip()
        return content.strip()

    @staticmethod
    def _create_prompt() -> ChatPromptTemplate:
        system_prompt = """你是 AHU / 楼控架构规划 advisor。你的任务是在 deterministic draft 基础上给出结构化补丁建议。

约束：
- 不允许输出最终 flows JSON。
- 不允许发明 template_id、pattern_id、module_type 或不存在的 subsystem_id。
- 不允许删除 deterministic draft 中已有的必需页面或用户显式子系统。
- template_preferences 只能使用 candidate_templates 中已有 template_id。
- shared signal 归属不确定时写入 warnings，不要强行指定 owner。"""

        user_template = """requirement_spec：
{requirement_json}

selected_system_pattern：
{pattern_json}

candidate_templates：
{templates_json}

deterministic_draft：
{draft_json}

请输出 ArchitectureAdvice。"""
        return ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", user_template),
        ])

    def advise(
        self,
        *,
        requirement_spec: Dict[str, Any],
        selected_system_pattern: Dict[str, Any],
        candidate_templates: List[Dict[str, Any]],
        deterministic_draft: Dict[str, Any],
    ) -> Dict[str, Any]:
        """调用 LLM 并返回原始 advice 与诊断；采用和过滤由 planner 本地完成。"""

        start = time.perf_counter()
        diagnostics: Dict[str, Any] = {
            "enabled": True,
            "provider": self.provider,
            "model": self.model,
            "structured_output_used": False,
            "llm_used": False,
            "fallback_used": False,
            "fallback_reason": "",
            "elapsed_ms": 0,
        }
        messages = self.prompt.format_messages(
            requirement_json=json.dumps(requirement_spec or {}, ensure_ascii=False, sort_keys=True),
            pattern_json=json.dumps(selected_system_pattern or {}, ensure_ascii=False, sort_keys=True),
            templates_json=json.dumps(candidate_templates or [], ensure_ascii=False, sort_keys=True),
            draft_json=json.dumps(deterministic_draft or {}, ensure_ascii=False, sort_keys=True),
        )

        try:
            structured_llm = self.llm.with_structured_output(
                ArchitectureAdvice,
                method="function_calling",
            )
            response = structured_llm.invoke(messages)
            payload = _model_to_dict(_validate_payload(_model_to_dict(response)))
            diagnostics["structured_output_used"] = True
            diagnostics["llm_used"] = True
        except Exception as structured_error:
            try:
                response = self.llm.invoke(messages)
                raw = self._extract_json_text(getattr(response, "content", "") or "")
                payload = _model_to_dict(_validate_payload(json.loads(raw) if raw else {}))
                diagnostics["llm_used"] = True
                diagnostics["fallback_reason"] = f"structured_output_failed: {structured_error}"
            except Exception as parse_error:
                diagnostics["fallback_used"] = True
                diagnostics["fallback_reason"] = str(parse_error)
                diagnostics["elapsed_ms"] = int((time.perf_counter() - start) * 1000)
                return {
                    "advice": {},
                    "diagnostics": diagnostics,
                }

        diagnostics["elapsed_ms"] = int((time.perf_counter() - start) * 1000)
        diagnostics["confidence"] = payload.get("confidence", 0.0)
        diagnostics["patch_summary"] = {
            "page_patch_count": len(payload.get("page_patch", []) or []),
            "subsystem_patch_count": len(payload.get("subsystem_patch", []) or []),
            "template_preference_count": len(payload.get("template_preferences", {}) or {}),
            "shared_signal_patch_count": len(payload.get("shared_signal_patch", []) or []),
            "warning_count": len(payload.get("warnings", []) or []),
        }
        return {
            "advice": payload,
            "diagnostics": diagnostics,
        }
