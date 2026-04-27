"""Deterministic signal semantics helpers for template interface bindings."""
from __future__ import annotations

from typing import Any, Dict, Iterable, Sequence

from utils.phase3_adapters import normalize_signal_name


CANONICAL_SIGNAL_ALIASES: Dict[str, list[str]] = {
    "supply_fan_run_state": [
        "送风机运行状态",
        "送风机运行标志",
        "风机运行状态反馈",
        "supply_fan_run_state",
        "supply_fan_run_flag",
    ],
    "supply_fan_fault_state": [
        "送风机故障状态",
        "送风机故障标志",
        "风机故障状态",
        "风机故障标志",
        "supply_fan_fault_state",
        "supply_fan_fault_flag",
    ],
    "supply_fan_available": [
        "送风机可用标志",
        "控制使能",
        "supply_fan_available",
        "supply_fan_available_flag",
    ],
    "auto_manual_mode": [
        "手自动控制切换",
        "手/自动",
        "自动/手动",
        "送风机启停手/自动",
        "送风机频率手/自动",
        "冷水阀开度手/自动",
        "新风阀开度手/自动",
        "回风阀开度手/自动",
        "auto_manual_mode",
        "auto_manual",
    ],
    "local_remote_mode": [
        "本地/远程",
        "远程/本地",
        "送风机本地/远程",
        "local_remote_mode",
        "local_remote",
    ],
    "schedule_enable": [
        "schedule_enable",
        "定时启停",
        "定时使能",
    ],
}

KNOWN_SHARED_SIGNAL_KEYS = {
    "supply_fan_available",
}

_PARAMETER_KEYWORDS = (
    "设定值",
    "比例增益",
    "积分增益",
    "微分增益",
    "上限",
    "下限",
    "系数",
    "运算间隔",
    "延时",
    "配置",
    "死区",
    "p值",
    "i值",
    "d值",
)
_COMMAND_KEYWORDS = (
    "命令",
    "手动",
    "自动",
    "手/自动",
    "本地/远程",
    "复位",
    "切换",
)
_FEEDBACK_KEYWORDS = (
    "状态",
    "反馈",
    "故障",
    "压差",
    "温度",
    "co2",
    "湿度",
    "运行",
)

_ALIAS_LOOKUP: Dict[str, str] = {}
for canonical_key, aliases in CANONICAL_SIGNAL_ALIASES.items():
    for alias in aliases:
        normalized = normalize_signal_name(alias)
        if normalized:
            _ALIAS_LOOKUP[normalized] = canonical_key


def canonicalize_signal_name(value: Any) -> str:
    """Return a stable canonical key for a signal name when an alias is known."""
    normalized = normalize_signal_name(value)
    if not normalized:
        return ""
    return _ALIAS_LOOKUP.get(normalized, normalized)


def _canonical_keys(values: Iterable[Any] | None) -> set[str]:
    return {
        canonical_key
        for value in values or []
        if (canonical_key := canonicalize_signal_name(value))
    }


def _explicit_external_signal_keys(requirement_spec: Dict[str, Any] | None) -> set[str]:
    if not isinstance(requirement_spec, dict):
        return set()

    signals = requirement_spec.get("signals", {}) if isinstance(requirement_spec.get("signals"), dict) else {}
    candidates = []
    for key in ("inputs", "software_points"):
        values = signals.get(key, [])
        if isinstance(values, list):
            candidates.extend(values)
    global_modes = requirement_spec.get("global_modes", [])
    if isinstance(global_modes, list):
        candidates.extend(global_modes)
    return _canonical_keys(candidates)


def _contains_keyword(signal_name: str, keywords: Sequence[str]) -> bool:
    lowered = str(signal_name).strip().lower()
    return any(keyword in lowered for keyword in keywords)


def classify_template_input(
    signal_name: str,
    *,
    requirement_spec: Dict[str, Any] | None = None,
    shared_signal_keys: Iterable[Any] | None = None,
) -> Dict[str, Any]:
    """Classify a template input before it is projected into shared-signal logic."""
    signal_key = normalize_signal_name(signal_name)
    canonical_signal_key = canonicalize_signal_name(signal_name)
    explicit_external_keys = _explicit_external_signal_keys(requirement_spec)
    projected_shared_keys = _canonical_keys(shared_signal_keys) | set(KNOWN_SHARED_SIGNAL_KEYS)

    if canonical_signal_key in explicit_external_keys:
        return {
            "signal_key": signal_key,
            "canonical_signal_key": canonical_signal_key,
            "binding_kind": "external_input",
            "allowed_external": True,
            "evidence": ["Matched requirement_spec.signals/global_modes."],
            "confidence": 0.95,
        }
    if canonical_signal_key in projected_shared_keys:
        return {
            "signal_key": signal_key,
            "canonical_signal_key": canonical_signal_key,
            "binding_kind": "shared_signal",
            "allowed_external": False,
            "evidence": ["Matched known AHU cross-subsystem dependency."],
            "confidence": 0.9,
        }
    if _contains_keyword(signal_name, _PARAMETER_KEYWORDS):
        return {
            "signal_key": signal_key,
            "canonical_signal_key": canonical_signal_key,
            "binding_kind": "external_parameter",
            "allowed_external": True,
            "evidence": ["Matched parameter-style keyword."],
            "confidence": 0.86,
        }
    if _contains_keyword(signal_name, _COMMAND_KEYWORDS):
        return {
            "signal_key": signal_key,
            "canonical_signal_key": canonical_signal_key,
            "binding_kind": "external_command",
            "allowed_external": True,
            "evidence": ["Matched command/mode keyword."],
            "confidence": 0.84,
        }
    if _contains_keyword(signal_name, _FEEDBACK_KEYWORDS):
        return {
            "signal_key": signal_key,
            "canonical_signal_key": canonical_signal_key,
            "binding_kind": "external_input",
            "allowed_external": True,
            "evidence": ["Matched measurement/feedback keyword."],
            "confidence": 0.8,
        }
    return {
        "signal_key": signal_key,
        "canonical_signal_key": canonical_signal_key,
        "binding_kind": "external_input",
        "allowed_external": True,
        "evidence": ["Template input defaults to external_input in reuse path."],
        "confidence": 0.7,
    }


def classify_template_output(
    signal_name: str,
    *,
    consumer_signal_keys: Iterable[Any] | None = None,
    shared_signal_keys: Iterable[Any] | None = None,
) -> Dict[str, Any]:
    """Classify a template output as a cross-subsystem shared signal or local output."""
    signal_key = normalize_signal_name(signal_name)
    canonical_signal_key = canonicalize_signal_name(signal_name)
    projected_shared_keys = _canonical_keys(shared_signal_keys) | set(KNOWN_SHARED_SIGNAL_KEYS)
    consumer_keys = _canonical_keys(consumer_signal_keys)

    if canonical_signal_key in consumer_keys or canonical_signal_key in projected_shared_keys:
        return {
            "signal_key": signal_key,
            "canonical_signal_key": canonical_signal_key,
            "binding_kind": "shared_signal",
            "allowed_external": False,
            "evidence": ["Output is consumed by another subsystem or known shared dependency."],
            "confidence": 0.9,
        }
    return {
        "signal_key": signal_key,
        "canonical_signal_key": canonical_signal_key,
        "binding_kind": "subsystem_output",
        "allowed_external": False,
        "evidence": ["Output remains subsystem-local by default."],
        "confidence": 0.8,
    }
