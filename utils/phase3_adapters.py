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

_SUBSYSTEM_DEFAULT_IMPORTS: Dict[str, List[str]] = {
    "heater_control": ["送风机可用标志"],
    "chw_valve_control": ["送风机可用标志"],
    "dx_control": ["送风机可用标志"],
}

_GLOBAL_MODE_RULES: List[Tuple[str, Tuple[str, ...]]] = [
    ("auto_manual", ("自动", "manual", "手动", "手/自动", "auto")),
    ("season_mode", ("季节", "summer", "winter", "制冷", "制热", "夏季", "冬季")),
    ("schedule_enable", ("定时", "schedule", "时段", "时序", "启停时间")),
    ("local_remote", ("远程", "本地", "remote", "local")),
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


def _infer_global_modes(scenario: Dict[str, Any]) -> List[str]:
    joined = " ".join(_extract_candidate_texts(scenario)).lower()
    modes: List[str] = []
    for mode_name, keywords in _GLOBAL_MODE_RULES:
        if any(keyword in joined for keyword in keywords):
            modes.append(mode_name)
    return _dedupe_strings(modes)


def _infer_software_points(scenario: Dict[str, Any], global_modes: List[str]) -> List[str]:
    software_points: List[str] = list(global_modes)
    for text in _clean_text_list(scenario.get("input_signals", [])) + _clean_text_list(scenario.get("output_signals", [])):
        lowered = text.lower()
        if any(token in lowered for token in ("手/自动", "自动", "manual", "auto")):
            software_points.append("auto_manual")
        if any(token in lowered for token in ("远程", "本地", "remote", "local")):
            software_points.append("local_remote")
        if any(token in lowered for token in ("定时", "schedule", "时段")):
            software_points.append("schedule_enable")
    return _dedupe_strings(software_points)


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
        if not matching_inputs:
            matching_inputs.extend(_SUBSYSTEM_DEFAULT_IMPORTS.get(subsystem_type, []))
        subsystems.append(
            {
                "subsystem_id": subsystem_id,
                "subsystem_type": subsystem_type,
                "goal": goal,
                "page_hint": "控制",
                "priority": index,
                "preferred_templates": [],
                "imports": _dedupe_strings(matching_inputs),
                "exports": _dedupe_strings(matching_outputs),
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
    if any(mode == "schedule_enable" for mode in _infer_global_modes(scenario)):
        pages.append("定时")
    return _dedupe_strings(pages)


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
    global_modes = _infer_global_modes(scenario)
    input_signals = _dedupe_strings(_clean_text_list(scenario.get("input_signals", [])))
    output_signals = _dedupe_strings(_clean_text_list(scenario.get("output_signals", [])))
    software_points = _infer_software_points(scenario, global_modes)

    if not subsystems:
        warnings.append("未能从场景分析中可靠识别子系统边界。")
        ambiguities.append("缺少可用于拆分子系统的显式设备/执行器信息。")

    confidence = scenario.get("confidence", 0.0)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    if not summary:
        warnings.append("场景摘要为空，已回退到 analysis_result 的弱投影。")
        ambiguities.append("缺少可用于规划的稳定场景摘要。")
    if not system_type:
        warnings.append("未能从场景分析中识别系统类型。")
        ambiguities.append("system_type 未明确，后续规划可能退化为通用控制。")
    if confidence < 0.5:
        warnings.append("场景分析置信度偏低，子系统/页面/信号投影可能不稳定。")
        if "场景分析置信度偏低，需要人工复核关键约束。" not in ambiguities:
            ambiguities.append("场景分析置信度偏低，需要人工复核关键约束。")
    if not input_signals and not output_signals:
        warnings.append("未提取到显式输入/输出信号，部分共享信号可能只能靠规则补全。")

    requirement_spec.update(
        {
            "system_type": system_type,
            "scenario_summary": summary,
            "subsystems": subsystems,
            "signals": {
                "inputs": input_signals,
                "outputs": output_signals,
                "software_points": software_points,
                "alarm_points": _clean_text_list(scenario.get("interlocks_or_limits", [])),
            },
            "required_pages": _infer_required_pages(system_type, subsystems, scenario),
            "global_modes": global_modes,
            "ambiguities": _dedupe_strings(ambiguities),
            "assumptions": assumptions,
            "acceptance_criteria": _clean_text_list(scenario.get("interlocks_or_limits", [])),
            "confidence": confidence,
            "warnings": warnings,
        }
    )
    return requirement_spec


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
