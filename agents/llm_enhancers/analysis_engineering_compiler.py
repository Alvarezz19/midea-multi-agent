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
    target_profile: Dict[str, Any] = Field(default_factory=dict)
    retrieval_hints: Dict[str, Any] = Field(default_factory=dict)
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


def _looks_like_complex_ahu_request(query: str, requirement_spec: Dict[str, Any]) -> bool:
    text = " ".join([
        query or "",
        str((requirement_spec or {}).get("system_type", "") or ""),
        str((requirement_spec or {}).get("scenario_summary", "") or ""),
    ]).lower()
    ahu_hit = any(keyword in text for keyword in ("ahu", "空调箱", "组合式空调", "新风机组"))
    complexity_hits = sum(
        1
        for keyword in (
            "io",
            "通讯",
            "控制",
            "定时",
            "直膨",
            "故障",
            "联锁",
            "pid",
            "手动",
            "自动",
            "flows",
            "node-red",
        )
        if keyword in text
    )
    return bool(ahu_hit and complexity_hits >= 3)


def _build_complex_ahu_default_patch(query: str) -> Dict[str, Any]:
    """当真实 LLM 对复杂 AHU 返回空补丁时，补一份保守工程画像。"""

    del query
    subsystem_patches = [
        {
            "subsystem_id": "supply_fan_ctrl",
            "subsystem_type": "supply_fan_control",
            "goal": "送风机启停、运行反馈、故障联锁和可用状态控制",
            "imports": ["自动手动模式", "本地远程模式", "定时启停使能", "送风机故障"],
            "exports": ["送风机运行状态", "送风机可用标志", "送风机启停命令"],
            "priority": 1,
        },
        {
            "subsystem_id": "supply_fan_frequency_ctrl",
            "subsystem_type": "supply_fan_frequency_control",
            "goal": "送风机频率给定、反馈和上下限处理",
            "imports": ["送风机运行状态", "送风机频率设定", "送风机频率反馈"],
            "exports": ["送风机频率输出"],
            "priority": 2,
        },
        {
            "subsystem_id": "air_damper_ctrl",
            "subsystem_type": "air_damper_control",
            "goal": "新风阀/回风阀开度控制和联锁",
            "imports": ["自动手动模式", "送风机可用标志"],
            "exports": ["新风阀控制输出", "回风阀控制输出"],
            "priority": 3,
        },
        {
            "subsystem_id": "chw_valve_ctrl",
            "subsystem_type": "chw_valve_control",
            "goal": "冷水阀 PID 调节、手自动和上下限保护",
            "imports": ["送风温度反馈", "送风温度设定", "夏季模式", "送风机可用标志"],
            "exports": ["冷水阀控制输出"],
            "priority": 4,
        },
        {
            "subsystem_id": "heater_ctrl",
            "subsystem_type": "heater_control",
            "goal": "电加热启停、故障报警和联锁保护",
            "imports": ["冬季模式", "送风机可用标志", "电加热故障"],
            "exports": ["电加热控制输出"],
            "priority": 5,
        },
        {
            "subsystem_id": "dx_ctrl",
            "subsystem_type": "dx_control",
            "goal": "直膨机状态、故障、启停和联锁控制",
            "imports": ["直膨机故障", "送风机可用标志", "制冷需求"],
            "exports": ["直膨机启停命令", "直膨机运行状态"],
            "priority": 6,
        },
    ]
    points = [
        {"name": "送风机运行状态", "point_role": "status", "subsystem_id": "supply_fan_ctrl", "io_kind": "physical_input", "explicit": False, "confidence": 0.65},
        {"name": "送风机故障", "point_role": "alarm", "subsystem_id": "supply_fan_ctrl", "io_kind": "physical_input", "explicit": False, "confidence": 0.65},
        {"name": "送风机启停命令", "point_role": "command", "subsystem_id": "supply_fan_ctrl", "io_kind": "physical_output", "explicit": False, "confidence": 0.65},
        {"name": "送风机频率设定", "point_role": "setpoint", "subsystem_id": "supply_fan_frequency_ctrl", "io_kind": "software_point", "explicit": False, "confidence": 0.6},
        {"name": "送风机频率反馈", "point_role": "sensor", "subsystem_id": "supply_fan_frequency_ctrl", "io_kind": "physical_input", "explicit": False, "confidence": 0.6},
        {"name": "新风阀控制输出", "point_role": "actuator", "subsystem_id": "air_damper_ctrl", "io_kind": "physical_output", "explicit": False, "confidence": 0.6},
        {"name": "回风阀控制输出", "point_role": "actuator", "subsystem_id": "air_damper_ctrl", "io_kind": "physical_output", "explicit": False, "confidence": 0.6},
        {"name": "送风温度反馈", "point_role": "sensor", "subsystem_id": "chw_valve_ctrl", "io_kind": "physical_input", "explicit": False, "confidence": 0.65},
        {"name": "送风温度设定", "point_role": "setpoint", "subsystem_id": "chw_valve_ctrl", "io_kind": "software_point", "explicit": False, "confidence": 0.65},
        {"name": "冷水阀控制输出", "point_role": "actuator", "subsystem_id": "chw_valve_ctrl", "io_kind": "physical_output", "explicit": False, "confidence": 0.65},
        {"name": "电加热故障", "point_role": "alarm", "subsystem_id": "heater_ctrl", "io_kind": "physical_input", "explicit": False, "confidence": 0.6},
        {"name": "电加热控制输出", "point_role": "actuator", "subsystem_id": "heater_ctrl", "io_kind": "physical_output", "explicit": False, "confidence": 0.6},
        {"name": "直膨机故障", "point_role": "alarm", "subsystem_id": "dx_ctrl", "io_kind": "physical_input", "explicit": False, "confidence": 0.6},
        {"name": "直膨机启停命令", "point_role": "command", "subsystem_id": "dx_ctrl", "io_kind": "physical_output", "explicit": False, "confidence": 0.6},
    ]
    return {
        "system_type": "AHU",
        "project_summary": "复杂 AHU 空调箱标准控制程序，目标形态参考真实 flows_*.json 的多页签、多子流程和完整 body 结构。",
        "subsystem_patches": subsystem_patches,
        "required_pages": ["IO/通讯", "控制", "定时", "直膨机状态", "直膨机故障"],
        "global_modes": ["auto_manual", "local_remote", "schedule_enable", "season_mode"],
        "points": points,
        "control_loops": [
            {
                "loop_id": "chw_valve_pid_loop",
                "subsystem_id": "chw_valve_ctrl",
                "target": "冷水阀",
                "strategy": "pid",
                "pv_signal": "送风温度反馈",
                "sp_signal": "送风温度设定",
                "mv_signal": "冷水阀控制输出",
                "constraints": ["上下限保护", "手自动切换", "夏季模式使能"],
                "explicit": False,
                "confidence": 0.65,
            }
        ],
        "interlocks": [
            {
                "interlock_id": "fan_fault_stop_outputs",
                "subsystem_id": "supply_fan_ctrl",
                "condition": "送风机故障或不可用",
                "action": "联锁关闭冷水阀、电加热、直膨机和风阀输出",
                "severity": "stop",
                "explicit": False,
                "confidence": 0.6,
            },
            {
                "interlock_id": "heater_requires_fan",
                "subsystem_id": "heater_ctrl",
                "condition": "送风机未运行",
                "action": "禁止电加热输出",
                "severity": "inhibit",
                "explicit": False,
                "confidence": 0.6,
            },
        ],
        "communication": {"address_policy": "用户未提供具体通讯地址，禁止编造地址，仅生成逻辑点位。"},
        "target_profile": {
            "reference_shape": "AHU程序/flows_*.json",
            "expected_pages": ["IO/通讯", "控制", "定时", "直膨机状态", "直膨机故障"],
            "expected_subflow_count": 5,
            "expected_body_node_count_min": 230,
            "standard_object_groups": ["io_comm_points", "control_subflow_instances", "schedule_objects", "dx_status_objects", "dx_fault_objects"],
        },
        "retrieval_hints": {
            "pattern_queries": [
                "AHU IO通讯 控制 定时 直膨机状态 直膨机故障 标准页签 子流程 body",
                "AHU flows JSON tab subflow internal_flow_objects 直膨 故障 定时",
            ],
            "template_queries": [
                "送风机 标准控制 运行反馈 故障 启停 联锁 子流程",
                "送风机 频率控制 频率设定 频率反馈 上下限",
                "风阀 控制 新风阀 回风阀 开度 手自动",
                "冷水阀 PID PV SP MV 上下限 手自动",
                "电加热 控制 故障 联锁 送风机可用",
                "直膨机 控制 状态 故障 启停 联锁",
            ],
            "atomic_queries": ["PID limit switch hysteresis delayOn delayOff rsFlipflop quote modbusOutput bacipOutput"],
        },
        "acceptance_criteria": [
            "最终 JSON 应包含 tab、subflow、subflow 实例和完整 internal_flow_objects body。",
            "缺少通讯地址时不得编造地址，必须保留逻辑点位和缺失项。",
        ],
        "ambiguities": ["缺少点表、设备数量和通讯地址，生成结果只能作为逻辑模板。"],
        "missing_required_fields": ["missing_equipment_quantity", "missing_point_schedule", "missing_communication_address"],
        "confidence": 0.72,
    }


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
- 对复杂 AHU 完整程序请求，即使用户没有点表和地址，也必须输出保守逻辑点位、控制回路、联锁、target_profile 和 retrieval_hints；不能因为“不要编造地址”而返回空补丁。
- 逻辑点位允许 explicit=false、address_hint=""；通讯地址缺失必须写入 missing_communication_address。
- target_profile 用于描述目标 flows_*.json 形态，例如 expected_pages、expected_subflow_count、expected_body_node_count_min、standard_object_groups。
- retrieval_hints 必须按 pattern_queries、template_queries、atomic_queries 给出检索线索，不允许出现具体 template_id 或 pattern_id。
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
        deterministic_enrichment_used = False
        if not any(
            payload.get(key)
            for key in (
                "subsystem_patches",
                "points",
                "control_loops",
                "interlocks",
                "target_profile",
                "retrieval_hints",
                "missing_required_fields",
            )
        ) and _looks_like_complex_ahu_request(query, requirement_spec):
            payload = _build_complex_ahu_default_patch(query)
            deterministic_enrichment_used = True
        diagnostics["elapsed_ms"] = int((time.perf_counter() - start) * 1000)
        diagnostics["confidence"] = payload.get("confidence", 0.0)
        diagnostics["deterministic_enrichment_used"] = deterministic_enrichment_used
        diagnostics["patch_summary"] = {
            "point_count": len(payload.get("points", []) or []),
            "control_loop_count": len(payload.get("control_loops", []) or []),
            "interlock_count": len(payload.get("interlocks", []) or []),
            "missing_required_field_count": len(payload.get("missing_required_fields", []) or []),
            "target_profile_present": bool(payload.get("target_profile")),
            "retrieval_hint_count": sum(
                len(payload.get("retrieval_hints", {}).get(key, []) or [])
                for key in ("pattern_queries", "template_queries", "atomic_queries")
                if isinstance(payload.get("retrieval_hints", {}), dict)
            ),
        }
        return {
            "patch": payload,
            "diagnostics": diagnostics,
        }
