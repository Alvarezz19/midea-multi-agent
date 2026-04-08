"""Phase 3 compatibility helpers."""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, Iterable, List, Tuple

from utils.phase3_contracts import RequirementSubsystem, empty_requirement_spec


_SUBSYSTEM_RULES: List[Tuple[str, str, Tuple[str, ...], str]] = [
    ("supply_fan_ctrl", "supply_fan_control", ("送风机频率", "送风机", "supply fan", "supply_air_fan"), "送风机控制"),
    ("exhaust_fan_ctrl", "exhaust_fan_control", ("排风机", "排风", "exhaust fan", "exhaust"), "排风机控制"),
    ("chw_valve_ctrl", "chw_valve_control", ("冷水阀", "冷冻水阀", "冷水", "chw valve", "chilled water valve"), "冷水阀控制"),
    ("heater_ctrl", "heater_control", ("电加热", "加热器", "heater", "heating"), "电加热控制"),
    ("air_damper_ctrl", "air_damper_control", ("新风阀", "回风阀", "风阀", "co2", "damper"), "风阀/CO2 联动控制"),
    ("dx_ctrl", "dx_control", ("直膨", "dx"), "直膨控制"),
]


def _normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = unicodedata.normalize("NFKC", value).strip()
    return re.sub(r"\s+", " ", text)


def _clean_text_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    result: List[str] = []
    for item in value:
        text = _normalize_text(item)
        if text:
            result.append(text)
    return result


def _dedupe_strings(values: Iterable[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        text = _normalize_text(value)
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result


def _slugify(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).lower().strip()
    text = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def _infer_system_type(scenario: Dict[str, Any]) -> str:
    system_type = _normalize_text(scenario.get("system_type", ""))
    if system_type:
        return system_type

    joined = " ".join(
        _normalize_text(scenario.get(key, ""))
        for key in ("summary", "business_goal", "equipment_object", "actuator")
    ).lower()
    if "ahu" in joined or "空调箱" in joined or "组合式空调" in joined:
        return "AHU"
    return ""


def _extract_candidate_texts(scenario: Dict[str, Any]) -> List[str]:
    texts = [
        _normalize_text(scenario.get("summary", "")),
        _normalize_text(scenario.get("business_goal", "")),
        _normalize_text(scenario.get("equipment_object", "")),
        _normalize_text(scenario.get("actuator", "")),
        _normalize_text(scenario.get("controlled_variable", "")),
        _normalize_text(scenario.get("feedback_variable", "")),
        _normalize_text(scenario.get("setpoint_variable", "")),
        _normalize_text(scenario.get("output_signal", "")),
        _normalize_text(scenario.get("control_strategy", "")),
        _normalize_text(scenario.get("control_mode", "")),
    ]
    texts.extend(_clean_text_list(scenario.get("input_signals", [])))
    texts.extend(_clean_text_list(scenario.get("output_signals", [])))
    texts.extend(_clean_text_list(scenario.get("operating_conditions", [])))
    texts.extend(_clean_text_list(scenario.get("interlocks_or_limits", [])))
    return [text for text in texts if text]


def _infer_subsystems(scenario: Dict[str, Any]) -> List[RequirementSubsystem]:
    texts = _extract_candidate_texts(scenario)
    lowered_texts = [text.lower() for text in texts]
    subsystems: List[RequirementSubsystem] = []

    for index, (subsystem_id, subsystem_type, keywords, default_goal) in enumerate(_SUBSYSTEM_RULES, start=1):
        if not any(any(keyword in text for keyword in keywords) for text in lowered_texts):
            continue

        matching_inputs = [
            signal
            for signal in _clean_text_list(scenario.get("input_signals", []))
            if any(keyword in signal.lower() for keyword in keywords)
        ]
        matching_outputs = [
            signal
            for signal in _clean_text_list(scenario.get("output_signals", []))
            if any(keyword in signal.lower() for keyword in keywords)
        ]
        goal = _normalize_text(scenario.get("business_goal", "")) or default_goal
        subsystems.append(
            {
                "subsystem_id": subsystem_id,
                "subsystem_type": subsystem_type,
                "goal": goal,
                "page_hint": "控制",
                "priority": index,
                "preferred_templates": [],
                "imports": matching_inputs,
                "exports": matching_outputs,
                "reasoning": f"Detected from scenario fields matching {subsystem_type}.",
            }
        )

    return subsystems


def _infer_required_pages(system_type: str, subsystems: List[RequirementSubsystem], scenario: Dict[str, Any]) -> List[str]:
    pages: List[str] = []
    if system_type.upper() == "AHU":
        pages.extend(["IO/通讯", "控制", "定时"])

    subsystem_types = {item.get("subsystem_type", "") for item in subsystems}
    if "dx_control" in subsystem_types:
        pages.append("直膨机状态")
    if "exhaust_fan_control" in subsystem_types:
        pages.append("排风机")

    texts = _extract_candidate_texts(scenario)
    if any("故障" in text for text in texts):
        pages.append("故障")
    if any("状态" in text for text in texts) and "直膨机状态" not in pages:
        pages.append("状态")
    return _dedupe_strings(pages)


def _infer_global_modes(scenario: Dict[str, Any]) -> List[str]:
    joined = " ".join(_extract_candidate_texts(scenario)).lower()
    modes: List[str] = []
    if any(token in joined for token in ("自动", "manual", "手动", "手/自动")):
        modes.append("auto_manual")
    if any(token in joined for token in ("季节", "summer", "winter", "制冷", "制热", "夏季", "冬季")):
        modes.append("season_mode")
    if any(token in joined for token in ("定时", "schedule", "时段")):
        modes.append("schedule_enable")
    if any(token in joined for token in ("远程", "本地", "remote", "local")):
        modes.append("local_remote")
    return _dedupe_strings(modes)


def build_requirement_spec(analysis_result: Dict[str, Any]) -> Dict[str, Any]:
    """Project analysis_result into the structured Phase 3 requirement_spec."""
    scenario = analysis_result.get("scenario_analysis", {}) if isinstance(analysis_result, dict) else {}
    if not isinstance(scenario, dict):
        scenario = {}

    requirement_spec = empty_requirement_spec()
    subsystems = _infer_subsystems(scenario)
    system_type = _infer_system_type(scenario)
    summary = _normalize_text(scenario.get("summary", ""))
    ambiguities = _dedupe_strings(_clean_text_list(scenario.get("ambiguities", [])))
    assumptions = _dedupe_strings(_clean_text_list(scenario.get("assumptions", [])))
    warnings: List[str] = []

    if not subsystems:
        warnings.append("未能从场景分析中可靠识别子系统边界。")
        ambiguities.append("缺少可用于拆分子系统的显式设备/执行器信息。")

    confidence = scenario.get("confidence", 0.0)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0

    requirement_spec.update(
        {
            "system_type": system_type,
            "scenario_summary": summary,
            "subsystems": subsystems,
            "signals": {
                "inputs": _clean_text_list(scenario.get("input_signals", [])),
                "outputs": _clean_text_list(scenario.get("output_signals", [])),
                "software_points": [],
                "alarm_points": _clean_text_list(scenario.get("interlocks_or_limits", [])),
            },
            "required_pages": _infer_required_pages(system_type, subsystems, scenario),
            "global_modes": _infer_global_modes(scenario),
            "ambiguities": _dedupe_strings(ambiguities),
            "assumptions": assumptions,
            "acceptance_criteria": _clean_text_list(scenario.get("interlocks_or_limits", [])),
            "confidence": max(0.0, min(1.0, confidence)),
            "warnings": warnings,
        }
    )
    return requirement_spec


def _ordered_subsystem_ids(architecture_plan: Dict[str, Any], subsystem_plan_map: Dict[str, Dict[str, Any]]) -> List[str]:
    ordered: List[str] = []
    for slot in architecture_plan.get("subsystem_slots", []) or []:
        subsystem_id = _normalize_text(slot.get("subsystem_id", ""))
        if subsystem_id and subsystem_id not in ordered and subsystem_id in subsystem_plan_map:
            ordered.append(subsystem_id)
    for subsystem_id in subsystem_plan_map.keys():
        if subsystem_id not in ordered:
            ordered.append(subsystem_id)
    return ordered


def build_legacy_execution_plan(
    requirement_spec: Dict[str, Any],
    architecture_plan: Dict[str, Any],
    subsystem_plan_map: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Build a flattened execution_plan projection for legacy verifier logic."""
    if not isinstance(subsystem_plan_map, dict) or not subsystem_plan_map:
        return {
            "goal": "规划失败: Phase 3 未生成任何子系统计划",
            "nodes": [],
            "connections": [],
        }

    nodes: List[Dict[str, Any]] = []
    connections: List[Dict[str, Any]] = []
    local_to_global: Dict[Tuple[str, str], str] = {}
    used_logic_ids = set()

    for subsystem_id in _ordered_subsystem_ids(architecture_plan, subsystem_plan_map):
        subsystem_plan = subsystem_plan_map.get(subsystem_id, {}) or {}
        for node in subsystem_plan.get("node_instances", []) or []:
            local_logic_id = _normalize_text(node.get("logic_id", "")) or f"{subsystem_id}_node_{len(nodes) + 1}"
            global_logic_id = local_logic_id
            if global_logic_id in used_logic_ids:
                global_logic_id = f"{subsystem_id}__{local_logic_id}"
            used_logic_ids.add(global_logic_id)
            local_to_global[(subsystem_id, local_logic_id)] = global_logic_id
            nodes.append(
                {
                    "logic_id": global_logic_id,
                    "module_type": _normalize_text(node.get("module_type", "")),
                    "parameters": dict(node.get("parameters", {}) or {}),
                    "reasoning": _normalize_text(node.get("reasoning", "")),
                }
            )

        for edge in subsystem_plan.get("edges", []) or []:
            from_node = local_to_global.get((subsystem_id, _normalize_text(edge.get("from_node", ""))))
            to_node = local_to_global.get((subsystem_id, _normalize_text(edge.get("to_node", ""))))
            if not from_node or not to_node:
                continue
            connections.append(
                {
                    "from_node": from_node,
                    "from_port_index": int(edge.get("from_port", 0) or 0),
                    "to_node": to_node,
                    "to_port_index": int(edge.get("to_port", 0) or 0),
                }
            )

    scenario_summary = _normalize_text(requirement_spec.get("scenario_summary", ""))
    goal = _normalize_text(architecture_plan.get("goal", "")) or scenario_summary or "Phase 3 兼容执行计划"
    if not nodes:
        goal = "规划失败: Phase 3 未生成任何节点"
    return {"goal": goal, "nodes": nodes, "connections": connections}


def make_page_key(label: str) -> str:
    normalized = _normalize_text(label)
    lowered = normalized.lower()
    if "io" in lowered or "通讯" in normalized or "通信" in normalized:
        return "io_comm"
    if "控制" in normalized:
        return "control"
    if "定时" in normalized:
        return "timing"
    if "状态" in normalized:
        return "status"
    if "故障" in normalized:
        return "fault"
    return _slugify(normalized) or "page"


def make_page_id(label: str) -> str:
    return f"page_{make_page_key(label)}"


def normalize_signal_name(value: Any) -> str:
    return _slugify(_normalize_text(value))
