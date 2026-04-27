from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from utils.ahu_knowledge_builder import load_ahu_flow_documents
from utils.phase6_diagnostics import END_STATES


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CASE_FILE_PATH = PROJECT_ROOT / "AHU程序" / "phase6_real_query_cases.json"
PATTERN_LIBRARY_ROOT = PROJECT_ROOT / "AHU程序" / "pattern_library"
REAL_QUERY_SUITE_OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "phase6_real_query_suite"
RETRIEVAL_EVAL_OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "phase6_retrieval_eval"

ALLOWED_CASE_TYPES = {"golden_success", "observed_success", "expected_repair", "expected_reject"}
ALLOWED_TRACE_POLICIES = {"keep_always", "keep_last_green", "keep_last_failure", "no_force_keep"}

SUBSYSTEM_LABELS = {
    "supply_fan_ctrl": "送风机",
    "exhaust_fan_ctrl": "排风机",
    "chw_valve_ctrl": "冷水阀",
    "heater_ctrl": "电加热",
    "air_damper_ctrl": "新风阀/回风阀/CO2",
    "dx_ctrl": "直膨",
}

SUBSYSTEM_TO_TEMPLATE_ROLES = {
    "supply_fan_ctrl": ("supply_fan_control",),
    "exhaust_fan_ctrl": ("exhaust_fan_control",),
    "chw_valve_ctrl": ("chw_valve_control",),
    "heater_ctrl": ("heater_control",),
    "air_damper_ctrl": ("air_damper_co2_control",),
    "dx_ctrl": ("dx_control",),
}

TEMPLATE_ROLE_SOURCE_HINTS = {
    "supply_fan_control": {
        "keywords": ("送风机", "supply fan", "supply_air_fan"),
        "pattern_page_keys": ("control", "supply_fan"),
    },
    "supply_fan_frequency_control": {
        "keywords": ("送风机频率", "变频", "frequency", "supply fan"),
        "pattern_page_keys": ("control", "supply_fan"),
    },
    "exhaust_fan_control": {
        "keywords": ("排风机", "排风", "exhaust fan", "exhaust"),
        "pattern_page_keys": ("exhaust_fan", "exhaust", "exhaust_status"),
    },
    "chw_valve_control": {
        "keywords": ("冷水阀", "冷冻水阀", "chw", "chilled water"),
        "pattern_page_keys": ("control", "chw_valve"),
    },
    "heater_control": {
        "keywords": ("电加热", "加热器", "heater", "heating"),
        "pattern_page_keys": ("control", "heater"),
    },
    "air_damper_co2_control": {
        "keywords": ("新风阀", "回风阀", "风阀", "co2", "damper"),
        "pattern_page_keys": ("control", "fresh_air"),
    },
    "dx_control": {
        "keywords": ("直膨", "dx"),
        "pattern_page_keys": ("control", "dx_status", "dx_fault"),
    },
}


@dataclass(frozen=True)
class Phase6RealQueryCase:
    case_id: str
    query: str
    case_type: str
    case_source: str
    stable_version: str
    expected_subsystems: tuple[str, ...]
    expected_min_subflow_count: int
    expected_verification_status: str
    expected_route_decision: str
    expected_failure_bucket: str
    allowed_end_states: tuple[str, ...]
    max_repair_rounds: int
    golden_trace_policy: str
    notes: str
    query_variants: tuple[str, ...] = ()
    expected_template_roles: tuple[str, ...] = ()
    expected_pattern_ids: tuple[str, ...] = ()


def _as_string(value: Any) -> str:
    return str(value or "").strip()


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    seen: set[str] = set()
    for item in value:
        normalized = _as_string(item)
        if normalized and normalized not in seen:
            items.append(normalized)
            seen.add(normalized)
    return items


def _as_non_negative_int(value: Any, *, field_name: str) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} 必须是非负整数") from exc
    if normalized < 0:
        raise ValueError(f"{field_name} 必须是非负整数")
    return normalized


def _normalized_lower_text(value: Any) -> str:
    return _as_string(value).lower()


def _matches_keywords(value: Any, keywords: tuple[str, ...]) -> bool:
    normalized = _normalized_lower_text(value)
    return bool(normalized and any(keyword.lower() in normalized for keyword in keywords))


def _relative_to_project(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path.resolve())


def _unique_strings(values: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _as_string(value)
        if normalized and normalized not in seen:
            ordered.append(normalized)
            seen.add(normalized)
    return ordered


def _validate_top_level(raw_payload: dict[str, Any]) -> None:
    required_keys = {"schema_version", "generated_at", "case_owner", "default_trace_policy", "cases"}
    missing = sorted(required_keys - set(raw_payload))
    if missing:
        raise ValueError(f"phase6 case 文件缺少顶层字段: {', '.join(missing)}")

    default_trace_policy = _as_string(raw_payload.get("default_trace_policy"))
    if default_trace_policy not in ALLOWED_TRACE_POLICIES:
        raise ValueError(f"default_trace_policy 非法: {default_trace_policy or '<empty>'}")

    cases = raw_payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("cases 必须是非空数组")


def _validate_case(raw_case: dict[str, Any], *, default_trace_policy: str, seen_case_ids: set[str]) -> Phase6RealQueryCase:
    required_fields = {
        "case_id",
        "query",
        "case_type",
        "case_source",
        "stable_version",
        "expected_subsystems",
        "expected_min_subflow_count",
        "expected_verification_status",
        "expected_route_decision",
        "expected_failure_bucket",
        "allowed_end_states",
        "max_repair_rounds",
        "golden_trace_policy",
        "notes",
    }
    missing = sorted(required_fields - set(raw_case))
    if missing:
        raise ValueError(f"case 缺少字段: {', '.join(missing)}")

    case_id = _as_string(raw_case.get("case_id"))
    if not case_id:
        raise ValueError("case_id 不能为空")
    if case_id in seen_case_ids:
        raise ValueError(f"case_id 重复: {case_id}")
    seen_case_ids.add(case_id)

    case_type = _as_string(raw_case.get("case_type"))
    if case_type not in ALLOWED_CASE_TYPES:
        raise ValueError(f"{case_id}: case_type 非法: {case_type or '<empty>'}")

    expected_subsystems = tuple(_as_string_list(raw_case.get("expected_subsystems")))
    if not expected_subsystems:
        raise ValueError(f"{case_id}: expected_subsystems 不能为空")

    allowed_end_states = tuple(_as_string_list(raw_case.get("allowed_end_states")))
    if not allowed_end_states:
        raise ValueError(f"{case_id}: allowed_end_states 不能为空")
    invalid_end_states = sorted(set(allowed_end_states) - END_STATES)
    if invalid_end_states:
        raise ValueError(f"{case_id}: allowed_end_states 非法: {', '.join(invalid_end_states)}")

    golden_trace_policy = _as_string(raw_case.get("golden_trace_policy")) or default_trace_policy
    if golden_trace_policy not in ALLOWED_TRACE_POLICIES:
        raise ValueError(f"{case_id}: golden_trace_policy 非法: {golden_trace_policy or '<empty>'}")

    return Phase6RealQueryCase(
        case_id=case_id,
        query=_as_string(raw_case.get("query")),
        case_type=case_type,
        case_source=_as_string(raw_case.get("case_source")),
        stable_version=_as_string(raw_case.get("stable_version")),
        expected_subsystems=expected_subsystems,
        expected_min_subflow_count=_as_non_negative_int(
            raw_case.get("expected_min_subflow_count"),
            field_name=f"{case_id}.expected_min_subflow_count",
        ),
        expected_verification_status=_as_string(raw_case.get("expected_verification_status")),
        expected_route_decision=_as_string(raw_case.get("expected_route_decision")),
        expected_failure_bucket=_as_string(raw_case.get("expected_failure_bucket")),
        allowed_end_states=allowed_end_states,
        max_repair_rounds=_as_non_negative_int(
            raw_case.get("max_repair_rounds"),
            field_name=f"{case_id}.max_repair_rounds",
        ),
        golden_trace_policy=golden_trace_policy,
        notes=_as_string(raw_case.get("notes")),
        query_variants=tuple(_as_string_list(raw_case.get("query_variants"))),
        expected_template_roles=tuple(_as_string_list(raw_case.get("expected_template_roles"))),
        expected_pattern_ids=tuple(_as_string_list(raw_case.get("expected_pattern_ids"))),
    )


def load_phase6_case_payload(case_file_path: str | Path | None = None) -> dict[str, Any]:
    case_path = Path(case_file_path) if case_file_path is not None else CASE_FILE_PATH
    raw_payload = json.loads(case_path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw_payload, dict):
        raise ValueError("phase6 case 文件顶层必须是对象")
    _validate_top_level(raw_payload)

    default_trace_policy = _as_string(raw_payload.get("default_trace_policy"))
    seen_case_ids: set[str] = set()
    raw_payload["cases"] = [
        _validate_case(raw_case, default_trace_policy=default_trace_policy, seen_case_ids=seen_case_ids)
        for raw_case in raw_payload.get("cases", [])
        if isinstance(raw_case, dict)
    ]
    return raw_payload


def load_phase6_cases(case_file_path: str | Path | None = None) -> tuple[dict[str, Any], list[Phase6RealQueryCase]]:
    payload = load_phase6_case_payload(case_file_path=case_file_path)
    return payload, list(payload["cases"])


def timestamp_token() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def resolve_template_roles(case: Phase6RealQueryCase) -> list[str]:
    if case.expected_template_roles:
        return list(case.expected_template_roles)

    ordered: list[str] = []
    seen: set[str] = set()
    for subsystem_id in case.expected_subsystems:
        for template_role in SUBSYSTEM_TO_TEMPLATE_ROLES.get(subsystem_id, ()):
            if template_role not in seen:
                ordered.append(template_role)
                seen.add(template_role)
    return ordered


def load_pattern_library_assets(
    pattern_library_root: str | Path | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    library_root = Path(pattern_library_root) if pattern_library_root is not None else PATTERN_LIBRARY_ROOT
    templates = json.loads((library_root / "subflow_templates.json").read_text(encoding="utf-8-sig"))
    patterns = json.loads((library_root / "system_patterns.json").read_text(encoding="utf-8-sig"))
    manifest = json.loads((library_root / "manifest.json").read_text(encoding="utf-8-sig"))
    return list(templates or []), list(patterns or []), dict(manifest or {})


def build_template_role_source_evidence(
    template_roles: list[str],
    *,
    pattern_library_root: str | Path | None = None,
) -> dict[str, dict[str, Any]]:
    requested_roles = _unique_strings(template_roles)
    if not requested_roles:
        return {}

    _, patterns, manifest = load_pattern_library_assets(pattern_library_root=pattern_library_root)
    flows_dir_value = _as_string(manifest.get("flows_dir"))
    flows_dir = PROJECT_ROOT / flows_dir_value if flows_dir_value else PROJECT_ROOT / "AHU程序"

    try:
        flow_documents = load_ahu_flow_documents(flows_dir)
    except Exception:
        flow_documents = []

    pattern_pages = []
    for pattern in patterns:
        for page in list(pattern.get("required_pages", []) or []) + list(pattern.get("optional_pages", []) or []):
            if not isinstance(page, dict):
                continue
            pattern_pages.append(
                {
                    "page_key": _as_string(page.get("page_key")),
                    "label": _as_string(page.get("label")),
                }
            )

    evidence_by_role: dict[str, dict[str, Any]] = {}
    for template_role in requested_roles:
        hints = TEMPLATE_ROLE_SOURCE_HINTS.get(template_role, {})
        keywords = tuple(hints.get("keywords", ()))
        pattern_page_keys = tuple(hints.get("pattern_page_keys", ()))

        matched_pattern_page_keys = _unique_strings(
            [
                page["page_key"]
                for page in pattern_pages
                if page["page_key"] in pattern_page_keys or _matches_keywords(page["label"], keywords)
            ]
        )
        matched_pattern_page_labels = _unique_strings(
            [
                page["label"]
                for page in pattern_pages
                if page["page_key"] in pattern_page_keys or _matches_keywords(page["label"], keywords)
            ]
        )

        source_flow_paths: list[str] = []
        source_flow_page_labels: list[str] = []
        matched_subflow_names: list[str] = []
        matched_object_names: list[str] = []
        adjacent_subflow_definition_names: list[str] = []

        for document in flow_documents:
            source_path = Path(document.get("source_path", ""))
            objects = document.get("objects", []) or []
            subflow_definitions = {
                _as_string(obj.get("id")): _as_string(obj.get("name"))
                for obj in objects
                if isinstance(obj, dict) and _as_string(obj.get("type")) == "subflow"
            }
            page_ids_to_labels = {
                _as_string(obj.get("id")): _as_string(obj.get("label"))
                for obj in objects
                if isinstance(obj, dict) and _as_string(obj.get("type")) == "tab"
            }
            flow_page_labels: list[str] = []
            flow_subflow_names: list[str] = []
            flow_object_names: list[str] = []
            flow_adjacent_subflow_definition_names: list[str] = []
            matched_page_ids: set[str] = set()

            for obj in objects:
                if not isinstance(obj, dict):
                    continue
                obj_type = _as_string(obj.get("type"))
                label_or_name = _as_string(obj.get("name") or obj.get("label"))
                if obj_type == "tab":
                    if _matches_keywords(obj.get("label"), keywords):
                        flow_page_labels.append(_as_string(obj.get("label")))
                        matched_page_ids.add(_as_string(obj.get("id")))
                    continue
                if not label_or_name or not _matches_keywords(label_or_name, keywords):
                    continue
                matched_page_ids.add(_as_string(obj.get("z")))
                if obj_type == "subflow":
                    flow_subflow_names.append(label_or_name)
                else:
                    flow_object_names.append(label_or_name)

            for obj in objects:
                if not isinstance(obj, dict):
                    continue
                obj_type = _as_string(obj.get("type"))
                if not obj_type.startswith("subflow:"):
                    continue
                if _as_string(obj.get("z")) not in matched_page_ids:
                    continue
                subflow_id = obj_type.split(":", 1)[1]
                definition_name = subflow_definitions.get(subflow_id)
                if definition_name:
                    flow_adjacent_subflow_definition_names.append(f"{definition_name}[{subflow_id}]")

            if flow_page_labels or flow_subflow_names or flow_object_names or flow_adjacent_subflow_definition_names:
                source_flow_paths.append(_relative_to_project(source_path))
                source_flow_page_labels.extend(flow_page_labels)
                matched_subflow_names.extend(flow_subflow_names)
                matched_object_names.extend(flow_object_names)
                adjacent_subflow_definition_names.extend(flow_adjacent_subflow_definition_names)

        source_evidence_found = bool(
            matched_pattern_page_keys
            or source_flow_paths
            or matched_subflow_names
            or matched_object_names
            or adjacent_subflow_definition_names
        )
        source_subflow_candidate_found = bool(matched_subflow_names)
        if source_subflow_candidate_found:
            likely_gap_stage = "role_named_subflow_present_but_not_indexed"
        elif adjacent_subflow_definition_names:
            likely_gap_stage = "source_context_with_adjacent_non_role_subflow"
        elif source_evidence_found:
            likely_gap_stage = "source_context_present_without_role_matched_template"
        else:
            likely_gap_stage = "no_source_evidence"

        evidence_by_role[template_role] = {
            "template_role": template_role,
            "source_evidence_found": source_evidence_found,
            "source_subflow_candidate_found": source_subflow_candidate_found,
            "likely_gap_stage": likely_gap_stage,
            "source_pattern_page_keys": matched_pattern_page_keys,
            "source_pattern_page_labels": matched_pattern_page_labels,
            "source_flow_paths": _unique_strings(source_flow_paths),
            "source_flow_page_labels": _unique_strings(source_flow_page_labels),
            "matched_subflow_names": _unique_strings(matched_subflow_names)[:5],
            "matched_object_names": _unique_strings(matched_object_names)[:5],
            "adjacent_subflow_definition_names": _unique_strings(adjacent_subflow_definition_names)[:5],
        }

    return evidence_by_role


def default_pattern_ids(patterns: list[dict[str, Any]]) -> list[str]:
    return [
        _as_string(pattern.get("pattern_id"))
        for pattern in patterns
        if _as_string(pattern.get("pattern_id"))
    ]


def build_retrieval_analysis_result(
    case: Phase6RealQueryCase,
    *,
    query_variants: list[str] | None = None,
) -> dict[str, Any]:
    variants = list(query_variants or []) or [case.query]
    subsystem_labels = [
        SUBSYSTEM_LABELS.get(subsystem_id, subsystem_id)
        for subsystem_id in case.expected_subsystems
    ]
    joined_labels = "、".join(subsystem_labels)
    business_goal = case.query or joined_labels or "AHU 控制生成"

    return {
        "retrieval_plan": {
            "queries": variants,
            "category_l1": "",
            "intent": "phase6_retrieval_eval",
            "detected_operations": [],
            "keywords": subsystem_labels,
        },
        "scenario_analysis": {
            "summary": case.query,
            "business_goal": business_goal,
            "system_type": "AHU",
            "equipment_object": joined_labels,
            "actuator": joined_labels,
            "controlled_variable": "",
            "feedback_variable": "",
            "setpoint_variable": "",
            "output_signal": joined_labels,
            "control_strategy": case.notes or "phase6_eval",
            "control_mode": "auto",
            "input_signals": [],
            "output_signals": [],
            "operating_conditions": [],
            "interlocks_or_limits": [],
            "calculation_logic": [],
            "ambiguities": [],
            "assumptions": [],
            "confidence": 1.0,
        },
    }


def write_json(path: str | Path, payload: Any) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_text(path: str | Path, content: str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def update_marker(path: str | Path, payload: dict[str, Any]) -> Path:
    marker_path = Path(path)
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return marker_path
