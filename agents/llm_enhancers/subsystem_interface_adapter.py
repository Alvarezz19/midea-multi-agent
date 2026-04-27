"""SubsystemPlanner 的可选 LLM 接口适配增强器。"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from utils.phase3_adapters import normalize_signal_name


ALLOWED_BINDING_KINDS = {
    "external_input",
    "subsystem_output",
    "shared_signal",
    "global_mode",
}


class PortBindingPatch(BaseModel):
    """模板端口绑定补丁。"""

    direction: str = ""
    port_index: int = 0
    template_port_name: str = ""
    signal_name: str = ""
    signal_key: str = ""
    binding_kind: str = ""
    allowed_external: bool = False
    owner_subsystem_id: str = ""
    confidence: float = 0.0
    reason: str = ""


class SubsystemInterfaceAdvice(BaseModel):
    """子系统接口适配建议。"""

    subsystem_id: str = ""
    selected_template_id: str = ""
    port_binding_patch: List[PortBindingPatch] = Field(default_factory=list)
    signal_aliases: Dict[str, str] = Field(default_factory=dict)
    missing_bindings: List[str] = Field(default_factory=list)
    fallback_required: bool = False
    fallback_reason: str = ""
    risk_flags: List[str] = Field(default_factory=list)


def _model_to_dict(model: Any) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    if hasattr(model, "dict"):
        return model.dict()
    return dict(model or {})


def _stringify_list_items(values: Any) -> List[str]:
    """兼容真实 LLM 将字符串列表项输出成对象的情况。"""

    if not isinstance(values, list):
        return []
    normalized: List[str] = []
    for item in values:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = str(
                item.get("signal_name")
                or item.get("template_port_name")
                or item.get("type")
                or item.get("reason")
                or item.get("message")
                or ""
            ).strip()
            if not text:
                text = json.dumps(item, ensure_ascii=False, sort_keys=True)
        else:
            text = str(item).strip()
        if text:
            normalized.append(text)
    return normalized


def _validate_payload(payload: Any) -> SubsystemInterfaceAdvice:
    if isinstance(payload, SubsystemInterfaceAdvice):
        return payload
    if isinstance(payload, dict):
        payload = dict(payload)
        payload["missing_bindings"] = _stringify_list_items(payload.get("missing_bindings", []))
        payload["risk_flags"] = _stringify_list_items(payload.get("risk_flags", []))
        if payload.get("fallback_reason") is None:
            payload["fallback_reason"] = ""
    if hasattr(SubsystemInterfaceAdvice, "model_validate"):
        return SubsystemInterfaceAdvice.model_validate(payload)
    return SubsystemInterfaceAdvice.parse_obj(payload)


class SubsystemInterfaceAdapter:
    """只输出受控接口补丁，不直接生成局部 IR。"""

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
    def _clean_text(value: Any) -> str:
        return value.strip() if isinstance(value, str) else ""

    @classmethod
    def _clean_text_list(cls, values: Any, limit: int = 20) -> List[str]:
        if not isinstance(values, list):
            return []
        result: List[str] = []
        seen = set()
        for value in values:
            text = cls._clean_text(value)
            if text and text not in seen:
                result.append(text)
                seen.add(text)
            if len(result) >= limit:
                break
        return result

    @staticmethod
    def _create_prompt() -> ChatPromptTemplate:
        system_prompt = """你是 AHU / 楼控子系统接口适配器。你的任务是根据子系统语义和模板端口合同，给出结构化端口绑定补丁。

约束：
- 只能使用输入中的当前 subsystem_id 和 template_id。
- 不允许输出最终 flows JSON，不允许生成 node_instances 或 wires。
- 不允许发明不存在的模板 ID、module_type 或端口编号。
- port_index 必须指向模板已有端口。
- binding_kind 只能是 external_input、subsystem_output、shared_signal、global_mode。
- 不确定时写入 risk_flags、missing_bindings 或 fallback_reason，不要强行绑定。"""

        user_template = """requirement_spec 摘要：
{requirement_json}

subsystem_descriptor：
{descriptor_json}

template_contract：
{template_json}

shared_signal_registry：
{registry_json}

available_atomic_modules 摘要：
{atomic_json}

请只输出合法 JSON 对象，字段符合 SubsystemInterfaceAdvice。"""
        return ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", user_template),
        ])

    def _invoke_json(self, messages: Any) -> Any:
        llm = self.llm
        if self.provider.lower() == "deepseek" and hasattr(llm, "bind"):
            llm = llm.bind(response_format={"type": "json_object"})
        return llm.invoke(messages)

    @staticmethod
    def _summarize_requirement(requirement_spec: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(requirement_spec, dict):
            return {}
        signals = requirement_spec.get("signals", {})
        if not isinstance(signals, dict):
            signals = {}
        return {
            "system_type": requirement_spec.get("system_type", ""),
            "signals": signals,
            "global_modes": list(requirement_spec.get("global_modes", []) or []),
            "acceptance_criteria": list(requirement_spec.get("acceptance_criteria", []) or []),
            "engineering": requirement_spec.get("engineering", {}) if isinstance(requirement_spec.get("engineering"), dict) else {},
        }

    @staticmethod
    def _summarize_atomic_modules(atomic_modules: Any, limit: int = 12) -> List[Dict[str, Any]]:
        if not isinstance(atomic_modules, list):
            return []
        result: List[Dict[str, Any]] = []
        for item in atomic_modules:
            if not isinstance(item, dict):
                continue
            result.append(
                {
                    "module_type": item.get("module_type", ""),
                    "name": item.get("name", ""),
                    "description": item.get("description", ""),
                    "ports_summary": item.get("ports_definition", {}),
                }
            )
            if len(result) >= limit:
                break
        return result

    def normalize_advice(
        self,
        payload: Dict[str, Any],
        *,
        subsystem_id: str,
        template_id: str,
        input_count: int,
        output_count: int,
    ) -> Dict[str, Any]:
        """按白名单和端口合同归一化 LLM 输出。"""

        selected_template_id = self._clean_text(payload.get("selected_template_id", ""))
        risk_flags = self._clean_text_list(payload.get("risk_flags", []))
        rejected_patches: List[Dict[str, Any]] = []
        invalid_template = bool(selected_template_id and selected_template_id != template_id)
        if invalid_template:
            risk_flags.append(f"invalid_selected_template_id:{selected_template_id}")

        normalized_patches: List[Dict[str, Any]] = []
        raw_patches = payload.get("port_binding_patch", [])
        if not isinstance(raw_patches, list):
            raw_patches = []

        for raw_patch in raw_patches:
            patch = _model_to_dict(raw_patch) if not isinstance(raw_patch, dict) else dict(raw_patch)
            reason = ""
            direction = self._clean_text(patch.get("direction", ""))
            try:
                port_index = int(patch.get("port_index", -1))
            except (TypeError, ValueError):
                port_index = -1
            binding_kind = self._clean_text(patch.get("binding_kind", ""))
            signal_name = self._clean_text(patch.get("signal_name", ""))
            try:
                confidence = float(patch.get("confidence", 0.0) or 0.0)
            except (TypeError, ValueError):
                confidence = 0.0

            if invalid_template:
                reason = "selected_template_id_not_allowed"
            elif direction not in {"input", "output"}:
                reason = "invalid_direction"
            elif direction == "input" and not (0 <= port_index < input_count):
                reason = "input_port_index_out_of_range"
            elif direction == "output" and not (0 <= port_index < output_count):
                reason = "output_port_index_out_of_range"
            elif binding_kind not in ALLOWED_BINDING_KINDS:
                reason = "invalid_binding_kind"
            elif not signal_name:
                reason = "empty_signal_name"
            elif confidence < 0.5:
                reason = "low_confidence"

            if reason:
                rejected_patches.append(
                    {
                        "direction": direction,
                        "port_index": port_index,
                        "signal_name": signal_name,
                        "reason": reason,
                    }
                )
                continue

            signal_key = self._clean_text(patch.get("signal_key", "")) or normalize_signal_name(signal_name)
            normalized_patches.append(
                {
                    "direction": direction,
                    "port_index": port_index,
                    "template_port_name": self._clean_text(patch.get("template_port_name", "")),
                    "signal_name": signal_name,
                    "signal_key": signal_key,
                    "binding_kind": binding_kind,
                    "allowed_external": bool(patch.get("allowed_external", False)),
                    "owner_subsystem_id": self._clean_text(patch.get("owner_subsystem_id", "")),
                    "confidence": max(0.0, min(1.0, confidence)),
                    "reason": self._clean_text(patch.get("reason", "")),
                }
            )

        return {
            "subsystem_id": subsystem_id,
            "selected_template_id": selected_template_id if selected_template_id == template_id else "",
            "port_binding_patch": normalized_patches,
            "signal_aliases": {
                self._clean_text(key): self._clean_text(value)
                for key, value in (payload.get("signal_aliases", {}) or {}).items()
                if self._clean_text(key) and self._clean_text(value)
            } if isinstance(payload.get("signal_aliases", {}), dict) else {},
            "missing_bindings": self._clean_text_list(payload.get("missing_bindings", [])),
            "fallback_required": bool(payload.get("fallback_required", False)),
            "fallback_reason": self._clean_text(payload.get("fallback_reason", "")),
            "risk_flags": risk_flags,
            "rejected_patches": rejected_patches,
        }

    def adapt(
        self,
        *,
        requirement_spec: Dict[str, Any],
        subsystem_descriptor: Dict[str, Any],
        template_contract: Dict[str, Any],
        shared_signal_registry: Dict[str, Dict[str, Any]] | List[Dict[str, Any]],
        available_atomic_modules: List[Dict[str, Any]],
        input_count: int,
        output_count: int,
    ) -> Dict[str, Any]:
        """调用 LLM 并返回归一化 advice 与诊断。"""

        subsystem_id = self._clean_text(subsystem_descriptor.get("subsystem_id", ""))
        template_id = self._clean_text(template_contract.get("template_id", ""))
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
            requirement_json=json.dumps(self._summarize_requirement(requirement_spec), ensure_ascii=False, sort_keys=True),
            descriptor_json=json.dumps(subsystem_descriptor or {}, ensure_ascii=False, sort_keys=True),
            template_json=json.dumps(template_contract or {}, ensure_ascii=False, sort_keys=True),
            registry_json=json.dumps(shared_signal_registry or {}, ensure_ascii=False, sort_keys=True),
            atomic_json=json.dumps(self._summarize_atomic_modules(available_atomic_modules), ensure_ascii=False, sort_keys=True),
        )

        try:
            if self.provider.lower() == "deepseek":
                raise RuntimeError("structured_output_skipped_for_deepseek_json_mode")
            structured_llm = self.llm.with_structured_output(
                SubsystemInterfaceAdvice,
                method="function_calling",
            )
            response = structured_llm.invoke(messages)
            payload = _model_to_dict(_validate_payload(_model_to_dict(response)))
            diagnostics["structured_output_used"] = True
            diagnostics["llm_used"] = True
        except Exception as structured_error:
            try:
                response = self._invoke_json(messages)
                raw = self._extract_json_text(getattr(response, "content", "") or "")
                payload = _model_to_dict(_validate_payload(json.loads(raw) if raw else {}))
                diagnostics["llm_used"] = True
                diagnostics["fallback_reason"] = f"structured_output_failed: {structured_error}"
            except Exception as parse_error:
                diagnostics["fallback_used"] = True
                diagnostics["fallback_reason"] = str(parse_error)
                diagnostics["elapsed_ms"] = int((time.perf_counter() - start) * 1000)
                return {
                    "advice": {
                        "subsystem_id": subsystem_id,
                        "selected_template_id": "",
                        "port_binding_patch": [],
                        "signal_aliases": {},
                        "missing_bindings": [],
                        "fallback_required": False,
                        "fallback_reason": "",
                        "risk_flags": [],
                        "rejected_patches": [],
                    },
                    "diagnostics": diagnostics,
                }

        if self._clean_text(payload.get("subsystem_id", "")) != subsystem_id:
            diagnostics["fallback_used"] = True
            diagnostics["fallback_reason"] = "subsystem_id_mismatch"
            normalized = {
                "subsystem_id": subsystem_id,
                "selected_template_id": "",
                "port_binding_patch": [],
                "signal_aliases": {},
                "missing_bindings": [],
                "fallback_required": False,
                "fallback_reason": "",
                "risk_flags": ["subsystem_id_mismatch"],
                "rejected_patches": [],
            }
        else:
            normalized = self.normalize_advice(
                payload,
                subsystem_id=subsystem_id,
                template_id=template_id,
                input_count=input_count,
                output_count=output_count,
            )

        diagnostics["elapsed_ms"] = int((time.perf_counter() - start) * 1000)
        diagnostics["patch_count"] = len(normalized.get("port_binding_patch", []) or [])
        diagnostics["rejected_patch_count"] = len(normalized.get("rejected_patches", []) or [])
        diagnostics["fallback_required"] = bool(normalized.get("fallback_required", False))
        return {
            "advice": normalized,
            "diagnostics": diagnostics,
        }
