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

_SUBSYSTEM_TYPE_TO_ID: Dict[str, str] = {
    "supply_fan_control": "supply_fan_ctrl",
    "exhaust_fan_control": "exhaust_fan_ctrl",
    "chw_valve_control": "chw_valve_ctrl",
    "heater_control": "heater_ctrl",
    "air_damper_control": "air_damper_ctrl",
    "dx_control": "dx_ctrl",
}

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


def _append_unique_strings(target: List[str], values: Iterable[Any]) -> List[str]:
    return _dedupe_strings(list(target or []) + [_normalize_text(value) for value in values])


def _safe_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = 0.0
    return max(0.0, min(1.0, confidence))


def _is_empty_engineering_patch(patch: Dict[str, Any]) -> bool:
    if not isinstance(patch, dict):
        return True
    scalar_keys = ("system_type", "project_summary")
    list_keys = (
        "subsystem_patches",
        "required_pages",
        "global_modes",
        "points",
        "control_loops",
        "interlocks",
        "acceptance_criteria",
        "ambiguities",
        "assumptions",
        "missing_required_fields",
    )
    dict_keys = ("communication", "naming_convention")
    if any(_normalize_text(patch.get(key, "")) for key in scalar_keys):
        return False
    if any(patch.get(key) for key in list_keys + dict_keys):
        return False
    return True


def _slugify(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).lower().strip()
    text = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def _merge_engineering_items(existing: List[Dict[str, Any]], incoming: List[Dict[str, Any]], key_fields: Tuple[str, ...]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = [dict(item) for item in existing if isinstance(item, dict)]
    seen = {
        tuple(_normalize_text(item.get(field, "")).lower() for field in key_fields)
        for item in result
    }
    for item in incoming:
        if not isinstance(item, dict):
            continue
        cleaned = {key: value for key, value in item.items() if value not in (None, "", [], {})}
        key = tuple(_normalize_text(cleaned.get(field, "")).lower() for field in key_fields)
        if not any(key) or key in seen:
            continue
        result.append(cleaned)
        seen.add(key)
    return result


def _normalize_subsystem_patch(payload: Dict[str, Any], fallback_priority: int) -> RequirementSubsystem | None:
    if not isinstance(payload, dict):
        return None

    subsystem_type = _normalize_text(payload.get("subsystem_type", ""))
    subsystem_id = _normalize_text(payload.get("subsystem_id", ""))
    if not subsystem_id and subsystem_type:
        subsystem_id = _SUBSYSTEM_TYPE_TO_ID.get(subsystem_type, "")
    if not subsystem_id:
        name_hint = _normalize_text(payload.get("name", "")) or _normalize_text(payload.get("goal", ""))
        subsystem_id = _slugify(name_hint)
    if not subsystem_id:
        return None

    goal = _normalize_text(payload.get("goal", "")) or _normalize_text(payload.get("name", ""))
    if not goal:
        goal = subsystem_type or subsystem_id

    priority = payload.get("priority", fallback_priority)
    try:
        priority = int(priority)
    except (TypeError, ValueError):
        priority = fallback_priority

    return {
        "subsystem_id": subsystem_id,
        "subsystem_type": subsystem_type or subsystem_id,
        "goal": goal,
        "page_hint": _normalize_text(payload.get("page_hint", "")) or "控制",
        "priority": priority,
        "preferred_templates": [],
        "imports": _clean_text_list(payload.get("imports", [])),
        "exports": _clean_text_list(payload.get("exports", [])),
        "reasoning": _normalize_text(payload.get("reasoning", "")) or "Merged from engineering requirement patch.",
    }


def _merge_subsystems(existing: List[RequirementSubsystem], incoming: List[Dict[str, Any]]) -> List[RequirementSubsystem]:
    result: List[RequirementSubsystem] = [dict(item) for item in existing if isinstance(item, dict)]
    by_id = {str(item.get("subsystem_id", "")).strip(): item for item in result}
    next_priority = len(result) + 1
    for raw_item in incoming:
        item = _normalize_subsystem_patch(raw_item, next_priority)
        if not item:
            continue
        subsystem_id = item["subsystem_id"]
        existing_item = by_id.get(subsystem_id)
        if existing_item:
            existing_item["imports"] = _append_unique_strings(existing_item.get("imports", []), item.get("imports", []))
            existing_item["exports"] = _append_unique_strings(existing_item.get("exports", []), item.get("exports", []))
            if not _normalize_text(existing_item.get("goal", "")):
                existing_item["goal"] = item.get("goal", "")
            if not _normalize_text(existing_item.get("reasoning", "")):
                existing_item["reasoning"] = item.get("reasoning", "")
            continue
        result.append(item)
        by_id[subsystem_id] = item
        next_priority += 1
    return result


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


def merge_engineering_requirement_patch(
    requirement_spec: Dict[str, Any],
    patch: Dict[str, Any],
) -> Dict[str, Any]:
    """把 LLM 工程补丁合并到 requirement_spec，保持下游正式字段兼容。"""

    merged = dict(requirement_spec or {})
    if _is_empty_engineering_patch(patch):
        return merged

    patch = patch if isinstance(patch, dict) else {}
    confidence = _safe_confidence(patch.get("confidence", 0.0))

    patch_system_type = _normalize_text(patch.get("system_type", ""))
    if patch_system_type and not _normalize_text(merged.get("system_type", "")) and confidence >= 0.5:
        merged["system_type"] = patch_system_type

    project_summary = _normalize_text(patch.get("project_summary", ""))
    if project_summary and not _normalize_text(merged.get("scenario_summary", "")):
        merged["scenario_summary"] = project_summary

    merged["subsystems"] = _merge_subsystems(
        merged.get("subsystems", []) if isinstance(merged.get("subsystems", []), list) else [],
        patch.get("subsystem_patches", []) if isinstance(patch.get("subsystem_patches", []), list) else [],
    )
    merged["required_pages"] = _append_unique_strings(
        merged.get("required_pages", []) if isinstance(merged.get("required_pages", []), list) else [],
        patch.get("required_pages", []) if isinstance(patch.get("required_pages", []), list) else [],
    )
    merged["global_modes"] = _append_unique_strings(
        merged.get("global_modes", []) if isinstance(merged.get("global_modes", []), list) else [],
        patch.get("global_modes", []) if isinstance(patch.get("global_modes", []), list) else [],
    )
    merged["acceptance_criteria"] = _append_unique_strings(
        merged.get("acceptance_criteria", []) if isinstance(merged.get("acceptance_criteria", []), list) else [],
        patch.get("acceptance_criteria", []) if isinstance(patch.get("acceptance_criteria", []), list) else [],
    )
    merged["ambiguities"] = _append_unique_strings(
        merged.get("ambiguities", []) if isinstance(merged.get("ambiguities", []), list) else [],
        patch.get("ambiguities", []) if isinstance(patch.get("ambiguities", []), list) else [],
    )
    merged["assumptions"] = _append_unique_strings(
        merged.get("assumptions", []) if isinstance(merged.get("assumptions", []), list) else [],
        patch.get("assumptions", []) if isinstance(patch.get("assumptions", []), list) else [],
    )
    merged["warnings"] = _append_unique_strings(
        merged.get("warnings", []) if isinstance(merged.get("warnings", []), list) else [],
        [],
    )

    signals = dict(merged.get("signals", {}) if isinstance(merged.get("signals", {}), dict) else {})
    for key in ("inputs", "outputs", "software_points", "alarm_points"):
        signals[key] = list(signals.get(key, []) if isinstance(signals.get(key, []), list) else [])

    points = patch.get("points", []) if isinstance(patch.get("points", []), list) else []
    for point in points:
        if not isinstance(point, dict):
            continue
        name = _normalize_text(point.get("name", ""))
        if not name:
            continue
        role = _normalize_text(point.get("point_role", "")).lower()
        io_kind = _normalize_text(point.get("io_kind", "")).lower()
        if role in {"alarm"}:
            signals["alarm_points"] = _append_unique_strings(signals["alarm_points"], [name])
        elif role in {"actuator", "command"} or io_kind == "physical_output":
            signals["outputs"] = _append_unique_strings(signals["outputs"], [name])
        elif role in {"setpoint", "mode", "parameter"} or io_kind == "software_point":
            signals["software_points"] = _append_unique_strings(signals["software_points"], [name])
        elif role in {"sensor", "status"} or io_kind in {"physical_input", "communication_point"}:
            signals["inputs"] = _append_unique_strings(signals["inputs"], [name])

    control_loops = patch.get("control_loops", []) if isinstance(patch.get("control_loops", []), list) else []
    for loop in control_loops:
        if not isinstance(loop, dict):
            continue
        signals["inputs"] = _append_unique_strings(signals["inputs"], [loop.get("pv_signal", "")])
        signals["software_points"] = _append_unique_strings(signals["software_points"], [loop.get("sp_signal", "")])
        signals["outputs"] = _append_unique_strings(signals["outputs"], [loop.get("mv_signal", "")])
        target = _normalize_text(loop.get("target", ""))
        strategy = _normalize_text(loop.get("strategy", ""))
        if target or strategy:
            merged["acceptance_criteria"] = _append_unique_strings(
                merged.get("acceptance_criteria", []),
                [f"{target} {strategy} 控制回路".strip()],
            )

    interlocks = patch.get("interlocks", []) if isinstance(patch.get("interlocks", []), list) else []
    for interlock in interlocks:
        if not isinstance(interlock, dict):
            continue
        condition = _normalize_text(interlock.get("condition", ""))
        action = _normalize_text(interlock.get("action", ""))
        severity = _normalize_text(interlock.get("severity", "")).lower()
        if condition or action:
            merged["acceptance_criteria"] = _append_unique_strings(
                merged.get("acceptance_criteria", []),
                [f"{condition} -> {action}".strip(" ->")],
            )
        if "alarm" in severity or "报警" in action or "故障" in condition:
            signals["alarm_points"] = _append_unique_strings(signals["alarm_points"], [condition or action])

    merged["signals"] = signals

    missing_fields = _clean_text_list(patch.get("missing_required_fields", []))
    if missing_fields:
        merged["ambiguities"] = _append_unique_strings(merged.get("ambiguities", []), missing_fields)
        missing_messages = [f"工程需求缺少关键输入：{field}" for field in missing_fields]
        merged["warnings"] = _append_unique_strings(merged.get("warnings", []), missing_messages)

    engineering = dict(merged.get("engineering", {}) if isinstance(merged.get("engineering", {}), dict) else {})
    engineering["points"] = _merge_engineering_items(engineering.get("points", []), points, ("name", "subsystem_id", "point_role"))
    engineering["control_loops"] = _merge_engineering_items(
        engineering.get("control_loops", []),
        control_loops,
        ("loop_id", "target", "subsystem_id"),
    )
    engineering["interlocks"] = _merge_engineering_items(
        engineering.get("interlocks", []),
        interlocks,
        ("interlock_id", "condition", "action"),
    )
    if isinstance(patch.get("communication", {}), dict):
        engineering["communication"] = {**dict(engineering.get("communication", {}) or {}), **dict(patch.get("communication", {}) or {})}
    if isinstance(patch.get("naming_convention", {}), dict):
        engineering["naming_convention"] = {
            **dict(engineering.get("naming_convention", {}) or {}),
            **dict(patch.get("naming_convention", {}) or {}),
        }
    engineering["missing_required_fields"] = _append_unique_strings(
        engineering.get("missing_required_fields", []),
        missing_fields,
    )
    if confidence:
        engineering["confidence"] = max(_safe_confidence(engineering.get("confidence", 0.0)), confidence)
    merged["engineering"] = engineering

    merged["confidence"] = max(_safe_confidence(merged.get("confidence", 0.0)), confidence)
    return merged


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
