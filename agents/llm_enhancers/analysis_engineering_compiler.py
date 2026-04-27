"""Analysis 节点的 AHU 工程需求编译增强器。"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List, Optional

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field


class AhuPointSpec(BaseModel):
    """AHU 工程点位。"""

    name: str = ""
    point_role: str = ""
    subsystem_id: str = ""
    io_kind: str = ""
    protocol: str = ""
    address_hint: str = ""
    explicit: bool = False
    confidence: float = 0.0


class AhuControlLoopSpec(BaseModel):
    """AHU 控制回路。"""

    loop_id: str = ""
    subsystem_id: str = ""
    target: str = ""
    strategy: str = ""
    pv_signal: str = ""
    sp_signal: str = ""
    mv_signal: str = ""
    constraints: List[str] = Field(default_factory=list)
    explicit: bool = False
    confidence: float = 0.0


class AhuInterlockSpec(BaseModel):
    """AHU 联锁。"""

    interlock_id: str = ""
    subsystem_id: str = ""
    condition: str = ""
    action: str = ""
    severity: str = ""
    explicit: bool = False
    confidence: float = 0.0


class AhuRequirementPatch(BaseModel):
    """用于合并到 requirement_spec 的工程补丁。"""

    system_type: str = ""
    project_summary: str = ""
    subsystem_patches: List[Dict[str, Any]] = Field(default_factory=list)
    required_pages: List[str] = Field(default_factory=list)
    global_modes: List[str] = Field(default_factory=list)
    points: List[AhuPointSpec] = Field(default_factory=list)
    control_loops: List[AhuControlLoopSpec] = Field(default_factory=list)
    interlocks: List[AhuInterlockSpec] = Field(default_factory=list)
    communication: Dict[str, Any] = Field(default_factory=dict)
    naming_convention: Dict[str, Any] = Field(default_factory=dict)
    acceptance_criteria: List[str] = Field(default_factory=list)
    ambiguities: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    missing_required_fields: List[str] = Field(default_factory=list)
    confidence: float = 0.0


def _model_to_dict(model: Any) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    if hasattr(model, "dict"):
        return model.dict()
    return dict(model or {})


def _stringify_list_items(values: Any, *, preferred_keys: List[str] | None = None) -> List[str]:
    """兼容真实 LLM 将字符串列表项输出成对象的情况。"""

    if not isinstance(values, list):
        return []
    keys = preferred_keys or ["code", "message", "field", "reason", "description", "name"]
    normalized: List[str] = []
    for item in values:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            parts = [str(item.get(key, "") or "").strip() for key in keys]
            text = ":".join(part for part in parts if part)
            if not text:
                text = json.dumps(item, ensure_ascii=False, sort_keys=True)
        else:
            text = str(item).strip()
        if text:
            normalized.append(text)
    return normalized


def _validate_patch(payload: Any) -> AhuRequirementPatch:
    if isinstance(payload, AhuRequirementPatch):
        return payload
    if isinstance(payload, dict):
        payload = dict(payload)
        for key in ("required_pages", "global_modes", "acceptance_criteria", "ambiguities", "assumptions"):
            payload[key] = _stringify_list_items(payload.get(key, []))
        payload["missing_required_fields"] = _stringify_list_items(
            payload.get("missing_required_fields", []),
            preferred_keys=["code", "field", "message", "reason", "description"],
        )
    if hasattr(AhuRequirementPatch, "model_validate"):
        return AhuRequirementPatch.model_validate(payload)
    return AhuRequirementPatch.parse_obj(payload)


class EngineeringRequirementCompiler:
    """把自然语言需求编译成受控的工程需求补丁。"""

    def __init__(
        self,
        llm: Any,
        provider: str = "",
        model: str = "",
    ) -> None:
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
        system_prompt = """你是 AHU / 楼控工程需求编译器。你的任务是把用户自然语言需求和已有 analysis 结果，整理成结构化工程补丁。

约束：
- 只输出 schema 要求的字段，不要输出平台 flows JSON。
- 不得编造用户未给出的通讯地址、点位编号、设备数量或模板 ID。
- 对用户明确给出的点位、回路、联锁标记 explicit=true；保守推断标记 explicit=false。
- 不确定的信息写入 ambiguities 或 missing_required_fields。
- missing_required_fields 可使用稳定代码：missing_equipment_quantity、missing_point_schedule、missing_communication_address、missing_control_target、missing_pid_loop_signals。
- 对非 AHU / 非楼控 / 非自动化工程需求，返回空补丁并保持 confidence=0。"""

        user_template = """用户需求：
{query}

已有 analysis_result：
{analysis_json}

当前 requirement_spec：
{requirement_json}

请只输出合法 JSON 对象，字段符合 AhuRequirementPatch。"""

        return ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", user_template),
        ])

    def _invoke_json(self, messages: Any) -> Any:
        llm = self.llm
        if self.provider.lower() == "deepseek" and hasattr(llm, "bind"):
            llm = llm.bind(response_format={"type": "json_object"})
        return llm.invoke(messages)

    def compile_patch(
        self,
        query: str,
        analysis_result: Dict[str, Any],
        requirement_spec: Dict[str, Any],
    ) -> Dict[str, Any]:
        """调用 LLM 并返回补丁与诊断；失败时返回 fallback 诊断。"""

        messages = self.prompt.format_messages(
            query=query,
            analysis_json=json.dumps(analysis_result or {}, ensure_ascii=False, sort_keys=True),
            requirement_json=json.dumps(requirement_spec or {}, ensure_ascii=False, sort_keys=True),
        )
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

        try:
            if self.provider.lower() == "deepseek":
                raise RuntimeError("structured_output_skipped_for_deepseek_json_mode")
            structured_llm = self.llm.with_structured_output(
                AhuRequirementPatch,
                method="function_calling",
            )
            response = structured_llm.invoke(messages)
            patch = _validate_patch(_model_to_dict(response))
            diagnostics["structured_output_used"] = True
            diagnostics["llm_used"] = True
        except Exception as structured_error:
            try:
                response = self._invoke_json(messages)
                raw = self._extract_json_text(getattr(response, "content", "") or "")
                patch = _validate_patch(json.loads(raw) if raw else {})
                diagnostics["llm_used"] = True
                diagnostics["fallback_reason"] = f"structured_output_failed: {structured_error}"
            except Exception as parse_error:
                diagnostics["fallback_used"] = True
                diagnostics["fallback_reason"] = str(parse_error)
                diagnostics["elapsed_ms"] = int((time.perf_counter() - start) * 1000)
                return {
                    "patch": {},
                    "diagnostics": diagnostics,
                }

        payload = _model_to_dict(patch)
        diagnostics["elapsed_ms"] = int((time.perf_counter() - start) * 1000)
        diagnostics["confidence"] = payload.get("confidence", 0.0)
        diagnostics["patch_summary"] = {
            "point_count": len(payload.get("points", []) or []),
            "control_loop_count": len(payload.get("control_loops", []) or []),
            "interlock_count": len(payload.get("interlocks", []) or []),
            "missing_required_field_count": len(payload.get("missing_required_fields", []) or []),
        }
        return {
            "patch": payload,
            "diagnostics": diagnostics,
        }
