"""Phase 3 architecture planner."""
from __future__ import annotations

from typing import Any, Dict, List

import config
from utils.console_utils import safe_print as print
from utils.phase3_adapters import make_page_id, make_page_key, normalize_signal_name
from utils.phase3_contracts import empty_architecture_plan, empty_decomposition_result
from utils.retrieval_bundle_utils import (
    get_bundle_style_guides,
    get_bundle_subflow_templates,
    get_bundle_system_patterns,
)
from utils.signal_semantics import (
    KNOWN_SHARED_SIGNAL_KEYS,
    canonicalize_signal_name,
    classify_template_input,
    classify_template_output,
)


_SUBSYSTEM_PAGE_KEYWORDS = {
    "supply_fan_control": ("控制",),
    "exhaust_fan_control": ("排风机", "控制"),
    "chw_valve_control": ("控制",),
    "heater_control": ("控制",),
    "air_damper_control": ("控制",),
    "dx_control": ("直膨机状态", "状态", "控制"),
}

_SUBSYSTEM_TEMPLATE_KEYWORDS = {
    "supply_fan_control": ("送风机", "supply_fan", "fan_control"),
    "exhaust_fan_control": ("排风机", "exhaust", "fan_control"),
    "chw_valve_control": ("冷水阀", "chw", "valve"),
    "heater_control": ("电加热", "heater"),
    "air_damper_control": ("新风", "回风", "风阀", "damper", "co2"),
    "dx_control": ("直膨", "dx"),
}

_SUBSYSTEM_PATTERN_PAGE_KEYS = {
    "supply_fan_control": ("control",),
    "exhaust_fan_control": ("exhaust_fan", "control"),
    "chw_valve_control": ("control",),
    "heater_control": ("control",),
    "air_damper_control": ("control",),
    "dx_control": ("dx_status", "dx_fault", "control"),
}

_GLOBAL_MODE_PAGE_KEYS = {
    "schedule_enable": ("timing",),
    "auto_manual": ("control",),
    "season_mode": ("control",),
    "local_remote": ("status",),
}


class ArchitecturePlanner:
    """Build a deterministic system skeleton from requirement_spec and retrieval assets."""

    def __init__(self):
        if config.DEBUG:
            print("[ArchitecturePlanner] initialized")

    @staticmethod
    def _dedupe_signal_names(values: List[str]) -> List[str]:
        ordered: List[str] = []
        seen = set()
        for value in values:
            signal_name = str(value).strip()
            signal_key = normalize_signal_name(signal_name)
            if not signal_key or signal_key in seen:
                continue
            seen.add(signal_key)
            ordered.append(signal_name)
        return ordered

    @staticmethod
    def _requirement_page_keys(requirement_spec: Dict[str, Any]) -> set[str]:
        page_keys = {
            make_page_key(str(label).strip())
            for label in requirement_spec.get("required_pages", []) or []
            if str(label).strip()
        }

        subsystem_types = {
            str(item.get("subsystem_type", "")).strip()
            for item in requirement_spec.get("subsystems", []) or []
            if isinstance(item, dict)
        }
        for subsystem_type in subsystem_types:
            page_keys.update(_SUBSYSTEM_PATTERN_PAGE_KEYS.get(subsystem_type, ("control",)))

        for mode in requirement_spec.get("global_modes", []) or []:
            page_keys.update(_GLOBAL_MODE_PAGE_KEYS.get(str(mode).strip(), ()))

        signals = requirement_spec.get("signals", {}) if isinstance(requirement_spec.get("signals"), dict) else {}
        signal_texts = [
            str(item).strip()
            for key in ("inputs", "outputs", "alarm_points")
            for item in signals.get(key, []) or []
            if str(item).strip()
        ]
        if any("故障" in text for text in signal_texts):
            page_keys.add("fault")
        if any("状态" in text for text in signal_texts):
            page_keys.add("status")
        return {page_key for page_key in page_keys if page_key}

    @classmethod
    def _score_system_pattern(
        cls,
        pattern: Dict[str, Any],
        requirement_spec: Dict[str, Any],
        selected_pattern_id: str,
    ) -> Dict[str, Any]:
        pattern_id = str(pattern.get("pattern_id", "")).strip()
        pattern_page_keys = {
            str(page.get("page_key", "")).strip()
            for key in ("required_pages", "optional_pages")
            for page in pattern.get(key, []) or []
            if isinstance(page, dict) and str(page.get("page_key", "")).strip()
        }
        requirement_page_keys = cls._requirement_page_keys(requirement_spec)
        subsystem_types = {
            str(item.get("subsystem_type", "")).strip()
            for item in requirement_spec.get("subsystems", []) or []
            if isinstance(item, dict)
        }
        score = 0
        reasons: List[str] = []
        score_breakdown: Dict[str, Any] = {
            "system_type": 0,
            "required_pages": {"matched": [], "missing": [], "score": 0},
            "subsystem_type": {},
            "global_modes": {},
            "signals": {},
            "selected_case_pattern": 0,
        }

        requested_system_type = str(requirement_spec.get("system_type", "")).strip().upper()
        pattern_system_type = str(pattern.get("system_type", "")).strip().upper()
        if requested_system_type and pattern_system_type and requested_system_type == pattern_system_type:
            score += 6
            reasons.append("system_type 匹配")
            score_breakdown["system_type"] = 6

        matched_pages = sorted(pattern_page_keys & requirement_page_keys)
        if matched_pages:
            score += len(matched_pages) * 4
            reasons.append(f"命中页面键: {', '.join(matched_pages)}")
            score_breakdown["required_pages"]["matched"] = matched_pages
            score_breakdown["required_pages"]["score"] += len(matched_pages) * 4

        missing_pages = sorted(requirement_page_keys - pattern_page_keys)
        if missing_pages:
            score -= len(missing_pages) * 2
            reasons.append(f"缺少页面键: {', '.join(missing_pages)}")
            score_breakdown["required_pages"]["missing"] = missing_pages
            score_breakdown["required_pages"]["score"] -= len(missing_pages) * 2

        for subsystem_type in subsystem_types:
            related_page_keys = set(_SUBSYSTEM_PATTERN_PAGE_KEYS.get(subsystem_type, ()))
            matched = related_page_keys & pattern_page_keys
            missing = related_page_keys - pattern_page_keys
            delta = 0
            if matched:
                delta += len(matched) * 3
                reasons.append(f"{subsystem_type} 对应页面匹配: {', '.join(sorted(matched))}")
            if missing:
                delta -= len(missing) * 3
                reasons.append(f"{subsystem_type} 缺少页面支撑: {', '.join(sorted(missing))}")
            if delta:
                score += delta
                score_breakdown["subsystem_type"][subsystem_type] = {
                    "matched_page_keys": sorted(matched),
                    "missing_page_keys": sorted(missing),
                    "score": delta,
                }

        for mode in requirement_spec.get("global_modes", []) or []:
            mode_name = str(mode).strip()
            if not mode_name:
                continue
            related_page_keys = set(_GLOBAL_MODE_PAGE_KEYS.get(mode_name, ()))
            matched = sorted(related_page_keys & pattern_page_keys)
            missing = sorted(related_page_keys - pattern_page_keys)
            delta = 0
            if matched:
                delta += len(matched) * 2
                reasons.append(f"global_mode {mode_name} 页面支撑: {', '.join(matched)}")
            if missing:
                delta -= len(missing) * 2
                reasons.append(f"global_mode {mode_name} 缺少页面支撑: {', '.join(missing)}")
            if delta:
                score += delta
                score_breakdown["global_modes"][mode_name] = {
                    "matched_page_keys": matched,
                    "missing_page_keys": missing,
                    "score": delta,
                }

        signals = requirement_spec.get("signals", {}) if isinstance(requirement_spec.get("signals"), dict) else {}
        signal_texts = [
            str(item).strip()
            for key in ("inputs", "outputs", "software_points", "alarm_points")
            for item in signals.get(key, []) or []
            if str(item).strip()
        ]
        if signal_texts and "fault" in pattern_page_keys:
            fault_signals = [text for text in signal_texts if "故障" in text]
            if fault_signals:
                score += 1
                reasons.append("故障类 signals 存在，pattern 提供 fault 页面支撑")
                score_breakdown["signals"]["fault"] = {"matched": fault_signals, "score": 1}
        if signal_texts and "status" in pattern_page_keys:
            status_signals = [text for text in signal_texts if "状态" in text]
            if status_signals:
                score += 1
                reasons.append("状态类 signals 存在，pattern 提供 status 页面支撑")
                score_breakdown["signals"]["status"] = {"matched": status_signals, "score": 1}

        if selected_pattern_id and pattern_id == selected_pattern_id:
            score += 3
            reasons.append("selected_case_pattern_id 命中，作为强信号加分")
            score_breakdown["selected_case_pattern"] = 3

        return {
            "pattern_id": pattern_id,
            "score": score,
            "matched_pages": matched_pages,
            "missing_pages": missing_pages,
            "reasons": reasons,
            "score_breakdown": score_breakdown,
        }

    @classmethod
    def _select_system_pattern(
        cls,
        requirement_spec: Dict[str, Any],
        retrieval_bundle: Dict[str, Any],
    ) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
        patterns = get_bundle_system_patterns(retrieval_bundle)
        metadata = retrieval_bundle.get("metadata", {}) if isinstance(retrieval_bundle, dict) else {}
        selected_pattern_id = ""
        if isinstance(metadata, dict):
            selected_pattern_id = str(metadata.get("selected_case_pattern_id", "")).strip()

        score_cards = [
            cls._score_system_pattern(pattern, requirement_spec, selected_pattern_id)
            for pattern in patterns
        ]
        if score_cards:
            score_cards.sort(key=lambda item: (-item["score"], item["pattern_id"]))
            winner_id = score_cards[0]["pattern_id"]
            for pattern in patterns:
                if str(pattern.get("pattern_id", "")).strip() == winner_id:
                    return pattern, score_cards

        for pattern in patterns:
            if str(pattern.get("pattern_id", "")).strip() == selected_pattern_id:
                return pattern, score_cards
        return (patterns[0] if patterns else {}), score_cards

    @staticmethod
    def _pick_page_label(
        subsystem_type: str,
        subsystem: Dict[str, Any],
        pages: List[Dict[str, Any]],
    ) -> str:
        page_hint = str(subsystem.get("page_hint", "")).strip()
        page_labels = {page.get("label", "") for page in pages}
        if page_hint and page_hint in page_labels:
            return page_hint

        for candidate in _SUBSYSTEM_PAGE_KEYWORDS.get(subsystem_type, ("控制",)):
            if candidate in page_labels:
                return candidate

        return pages[0]["label"] if pages else "控制"

    @staticmethod
    def _extract_template_signals(template_doc: Dict[str, Any], direction: str) -> List[str]:
        return [item.get("label", "") for item in ArchitecturePlanner._extract_template_ports(template_doc, direction)]

    @staticmethod
    def _extract_template_ports(template_doc: Dict[str, Any], direction: str) -> List[Dict[str, Any]]:
        ports_definition = template_doc.get("ports_definition", {}) if isinstance(template_doc, dict) else {}
        if not isinstance(ports_definition, dict):
            return []
        port_items = ports_definition.get(direction, [])
        ports: List[Dict[str, Any]] = []
        for index, item in enumerate(port_items if isinstance(port_items, list) else []):
            label = str(item.get("label") or item.get("name") or "").strip()
            if label:
                ports.append(
                    {
                        "label": label,
                        "index": int(item.get("index", index) or index),
                    }
                )
        return ports

    @staticmethod
    def _merge_interface_ports(template_ports: List[Dict[str, Any]], explicit_signals: List[str]) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        seen = set()

        for port in template_ports:
            label = str(port.get("label", "")).strip()
            canonical_key = canonicalize_signal_name(label)
            dedupe_key = canonical_key or normalize_signal_name(label)
            if not label or not dedupe_key or dedupe_key in seen:
                continue
            merged.append({"label": label, "index": int(port.get("index", len(merged)) or len(merged))})
            seen.add(dedupe_key)

        for signal_name in explicit_signals:
            label = str(signal_name).strip()
            canonical_key = canonicalize_signal_name(label)
            dedupe_key = canonical_key or normalize_signal_name(label)
            if not label or not dedupe_key or dedupe_key in seen:
                continue
            merged.append({"label": label, "index": len(merged)})
            seen.add(dedupe_key)

        return merged

    @staticmethod
    def _requirement_signal_context(requirement_spec: Dict[str, Any], subsystem: Dict[str, Any]) -> set[str]:
        signals = requirement_spec.get("signals", {}) if isinstance(requirement_spec.get("signals"), dict) else {}
        values: List[Any] = []
        for key in ("inputs", "outputs", "software_points", "alarm_points"):
            values.extend(list(signals.get(key, []) or []))
        values.extend(list(requirement_spec.get("global_modes", []) or []))
        values.extend(list(subsystem.get("imports", []) or []))
        values.extend(list(subsystem.get("exports", []) or []))
        return {
            canonical_key
            for value in values
            if (canonical_key := canonicalize_signal_name(value))
        }

    @classmethod
    def _interface_signal_keys(
        cls,
        subsystem: Dict[str, Any],
        direction: str,
    ) -> set[str]:
        field_name = "imports" if direction == "input" else "exports"
        return {
            canonical_key
            for value in subsystem.get(field_name, []) or []
            if (canonical_key := canonicalize_signal_name(value))
        }

    @classmethod
    def _template_interface_signal_keys(
        cls,
        template: Dict[str, Any],
        direction: str,
    ) -> set[str]:
        port_direction = "inputs" if direction == "input" else "outputs"
        return {
            canonical_key
            for item in cls._extract_template_ports(template, port_direction)
            if (canonical_key := canonicalize_signal_name(item.get("label")))
        }

    @classmethod
    def _score_template_candidate(
        cls,
        subsystem: Dict[str, Any],
        template: Dict[str, Any],
        requirement_spec: Dict[str, Any],
        page_label: str,
    ) -> Dict[str, Any]:
        template_id = str(template.get("template_id") or template.get("module_type") or "").strip()
        subsystem_type = str(subsystem.get("subsystem_type", "")).strip()
        template_role = str(template.get("template_role", "")).strip()
        searchable = " ".join(
            str(template.get(key, "")).lower()
            for key in ("template_name", "template_role", "description", "category")
        )
        goal_text = " ".join(
            str(subsystem.get(key, "")).lower()
            for key in ("subsystem_type", "goal", "reasoning")
        )
        keywords = _SUBSYSTEM_TEMPLATE_KEYWORDS.get(subsystem_type, ())
        signal_context = cls._requirement_signal_context(requirement_spec, subsystem)
        template_input_ports = cls._extract_template_ports(template, "inputs")
        template_output_ports = cls._extract_template_ports(template, "outputs")
        template_ports = template_input_ports + template_output_ports
        template_signal_keys = {
            canonicalize_signal_name(item.get("label"))
            for item in template_ports
            if canonicalize_signal_name(item.get("label"))
        }
        expected_input_keys = cls._interface_signal_keys(subsystem, "input")
        expected_output_keys = cls._interface_signal_keys(subsystem, "output")
        template_input_signal_keys = cls._template_interface_signal_keys(template, "input")
        template_output_signal_keys = cls._template_interface_signal_keys(template, "output")
        global_mode_keys = {
            canonicalize_signal_name(value)
            for value in requirement_spec.get("global_modes", []) or []
            if canonicalize_signal_name(value)
        }

        score = 0
        reasons: List[str] = []
        score_breakdown: Dict[str, Any] = {
            "template_role": 0,
            "subsystem_type": 0,
            "keyword_overlap": {"matched": [], "score": 0},
            "signal_overlap": {"matched": [], "score": 0},
            "global_modes": {"matched": [], "score": 0},
            "interface_coverage": {
                "inputs": {"matched": [], "missing": [], "score": 0},
                "outputs": {"matched": [], "missing": [], "score": 0},
            },
            "interface_capacity": {"input_shortage": 0, "output_shortage": 0, "score": 0},
            "required_pages": {"page_hint": page_label, "score": 0},
            "preferred_template": 0,
        }

        preferred_template_ids = {
            str(item).strip()
            for item in subsystem.get("preferred_templates", []) or []
            if str(item).strip()
        }
        if template_id in preferred_template_ids:
            score += 100
            reasons.append("命中 requirement_spec.preferred_templates")
            score_breakdown["preferred_template"] = 100

        if template_role == subsystem_type:
            score += 20
            reasons.append("template_role 与 subsystem_type 精确匹配")
            score_breakdown["template_role"] = 20
            score_breakdown["subsystem_type"] = 20
        elif template_role and template_role.lower() in goal_text:
            score += 8
            reasons.append("template_role 在 subsystem goal/reasoning 中被命中")
            score_breakdown["template_role"] = 8

        matched_keywords = sorted({keyword for keyword in keywords if keyword.lower() in searchable})
        if matched_keywords:
            delta = len(matched_keywords) * 3
            score += delta
            reasons.append(f"关键词命中: {', '.join(matched_keywords)}")
            score_breakdown["keyword_overlap"] = {"matched": matched_keywords, "score": delta}

        matched_signals = sorted(signal_context & template_signal_keys)
        if matched_signals:
            delta = len(matched_signals) * 4
            score += delta
            reasons.append(f"signals/global_modes 与模板端口重合: {', '.join(matched_signals)}")
            score_breakdown["signal_overlap"] = {"matched": matched_signals, "score": delta}

        matched_modes = sorted(global_mode_keys & template_signal_keys)
        if matched_modes:
            delta = len(matched_modes) * 2
            score += delta
            reasons.append(f"global_modes 与模板端口重合: {', '.join(matched_modes)}")
            score_breakdown["global_modes"] = {"matched": matched_modes, "score": delta}

        for direction, expected_keys, template_keys in (
            ("inputs", expected_input_keys, template_input_signal_keys),
            ("outputs", expected_output_keys, template_output_signal_keys),
        ):
            if not expected_keys:
                continue
            matched_keys = sorted(expected_keys & template_keys)
            missing_keys = sorted(expected_keys - template_keys)
            delta = len(matched_keys) * 6 - len(missing_keys) * 8
            score += delta
            if matched_keys:
                reasons.append(f"{direction} 接口覆盖: {', '.join(matched_keys)}")
            if missing_keys:
                reasons.append(f"{direction} 接口缺失: {', '.join(missing_keys)}")
            score_breakdown["interface_coverage"][direction] = {
                "matched": matched_keys,
                "missing": missing_keys,
                "score": delta,
            }

        input_shortage = max(0, len(expected_input_keys) - len(template_input_ports))
        output_shortage = max(0, len(expected_output_keys) - len(template_output_ports))
        if input_shortage or output_shortage:
            delta = -(input_shortage + output_shortage) * 10
            score += delta
            if input_shortage:
                reasons.append(
                    f"模板输入端口不足: required={len(expected_input_keys)} actual={len(template_input_ports)}"
                )
            if output_shortage:
                reasons.append(
                    f"模板输出端口不足: required={len(expected_output_keys)} actual={len(template_output_ports)}"
                )
            score_breakdown["interface_capacity"] = {
                "input_shortage": input_shortage,
                "output_shortage": output_shortage,
                "score": delta,
            }

        required_pages = {str(value).strip() for value in requirement_spec.get("required_pages", []) or [] if str(value).strip()}
        if page_label and page_label in required_pages:
            score += 1
            reasons.append(f"subsystem page_hint={page_label} 属于 required_pages")
            score_breakdown["required_pages"]["score"] = 1

        return {
            "template_id": template_id,
            "score": score,
            "reasons": reasons,
            "score_breakdown": score_breakdown,
        }

    @classmethod
    def _rank_template_candidates(
        cls,
        subsystem: Dict[str, Any],
        subflow_templates: List[Dict[str, Any]],
        requirement_spec: Dict[str, Any],
        page_label: str,
    ) -> List[Dict[str, Any]]:
        scored_cards = [
            cls._score_template_candidate(subsystem, template, requirement_spec, page_label)
            for template in subflow_templates
            if str(template.get("template_id") or template.get("module_type") or "").strip()
        ]
        return sorted(scored_cards, key=lambda item: (-int(item.get("score", 0) or 0), item.get("template_id", "")))

    def _build_interface_bindings(
        self,
        requirement_spec: Dict[str, Any],
        subsystem: Dict[str, Any],
        template_doc: Dict[str, Any],
        projected_shared_signal_keys: set[str],
        consumer_signal_keys: set[str],
    ) -> List[Dict[str, Any]]:
        explicit_imports = self._dedupe_signal_names(list(subsystem.get("imports", []) or []))
        explicit_exports = self._dedupe_signal_names(list(subsystem.get("exports", []) or []))
        template_input_ports = self._extract_template_ports(template_doc, "inputs")
        template_output_ports = self._extract_template_ports(template_doc, "outputs")
        input_ports = (
            list(template_input_ports)
            if template_input_ports
            else [{"label": signal_name, "index": index} for index, signal_name in enumerate(explicit_imports)]
        )
        output_ports = (
            list(template_output_ports)
            if template_output_ports
            else [{"label": signal_name, "index": index} for index, signal_name in enumerate(explicit_exports)]
        )

        bindings: List[Dict[str, Any]] = []
        for port in input_ports:
            signal_name = str(port.get("label", "")).strip()
            if not signal_name:
                continue
            classification = classify_template_input(
                signal_name,
                requirement_spec=requirement_spec,
                shared_signal_keys=projected_shared_signal_keys,
            )
            bindings.append(
                {
                    "signal_name": signal_name,
                    "signal_key": classification["signal_key"],
                    "canonical_signal_key": classification["canonical_signal_key"],
                    "direction": "input",
                    "binding_kind": classification["binding_kind"],
                    "allowed_external": bool(classification["allowed_external"]),
                    "owner_subsystem_id": "",
                    "port_index": int(port.get("index", len(bindings)) or 0),
                    "evidence": list(classification.get("evidence", []) or []),
                    "confidence": float(classification.get("confidence", 0.0) or 0.0),
                }
            )

        for port in output_ports:
            signal_name = str(port.get("label", "")).strip()
            if not signal_name:
                continue
            classification = classify_template_output(
                signal_name,
                consumer_signal_keys=consumer_signal_keys,
                shared_signal_keys=projected_shared_signal_keys,
            )
            bindings.append(
                {
                    "signal_name": signal_name,
                    "signal_key": classification["signal_key"],
                    "canonical_signal_key": classification["canonical_signal_key"],
                    "direction": "output",
                    "binding_kind": classification["binding_kind"],
                    "allowed_external": bool(classification["allowed_external"]),
                    "owner_subsystem_id": "",
                    "port_index": int(port.get("index", len(bindings)) or 0),
                    "evidence": list(classification.get("evidence", []) or []),
                    "confidence": float(classification.get("confidence", 0.0) or 0.0),
                }
            )
        return bindings

    def _match_template_ids(
        self,
        subsystem: Dict[str, Any],
        subflow_templates: List[Dict[str, Any]],
    ) -> List[str]:
        preferred = subsystem.get("preferred_templates", [])
        preferred = preferred if isinstance(preferred, list) else []
        preferred_ids = [str(item).strip() for item in preferred if str(item).strip()]

        subsystem_type = str(subsystem.get("subsystem_type", "")).strip()
        goal_text = " ".join(
            str(subsystem.get(key, "")).lower()
            for key in ("subsystem_type", "goal", "reasoning")
        )
        keywords = _SUBSYSTEM_TEMPLATE_KEYWORDS.get(subsystem_type, ())
        scored: List[tuple[int, str]] = []
        for template in subflow_templates:
            template_id = str(template.get("template_id") or template.get("module_type") or "").strip()
            if not template_id:
                continue
            if template_id in preferred_ids:
                scored.append((100, template_id))
                continue

            searchable = " ".join(
                str(template.get(key, "")).lower()
                for key in ("template_name", "template_role", "description", "category")
            )
            template_role = str(template.get("template_role", "")).strip()
            score = 0
            if template_role == subsystem_type:
                score += 20
            score += sum(3 for keyword in keywords if keyword.lower() in searchable)
            if template_role and template_role.lower() in goal_text:
                score += 2
            if score > 0:
                scored.append((score, template_id))

        ordered: List[str] = []
        seen = set()
        for _, template_id in sorted(scored, key=lambda item: (-item[0], item[1])):
            if template_id not in seen:
                ordered.append(template_id)
                seen.add(template_id)
        return ordered

    @classmethod
    def _build_shared_signal_registry(
        cls,
        requirement_spec: Dict[str, Any],
        subsystem_descriptors: List[Dict[str, Any]],
        planning_order: List[str],
    ) -> tuple[List[Dict[str, Any]], List[str]]:
        external_signal_keys = {
            canonicalize_signal_name(value)
            for value in (
                list((requirement_spec.get("signals", {}) or {}).get("inputs", []) or [])
                + list((requirement_spec.get("signals", {}) or {}).get("software_points", []) or [])
                + list(requirement_spec.get("global_modes", []) or [])
            )
            if canonicalize_signal_name(value)
        }
        registry_by_key: Dict[str, Dict[str, Any]] = {}
        warnings: List[str] = []

        def ensure_entry(signal_name: str, signal_key: str, semantic_role: str) -> Dict[str, Any]:
            if not signal_key:
                return {}
            entry = registry_by_key.setdefault(
                signal_key,
                {
                    "signal_name": str(signal_name).strip() or signal_key,
                    "signal_key": signal_key,
                    "canonical_signal_key": signal_key,
                    "semantic_role": semantic_role,
                    "owner_subsystem_id": "",
                    "allowed_external": signal_key in external_signal_keys,
                    "required_exporter_count": 0 if signal_key in external_signal_keys else 1,
                    "consumers": [],
                    "candidate_exporters": [],
                    "resolution_status": "",
                    "resolution_evidence": [],
                    "source_reason": "",
                },
            )
            if semantic_role == "global_mode":
                entry["semantic_role"] = "global_mode"
            return entry

        for descriptor in subsystem_descriptors:
            subsystem_id = str(descriptor.get("subsystem_id", "")).strip()
            if not subsystem_id:
                continue
            for binding in descriptor.get("interface_bindings", []) or []:
                if not isinstance(binding, dict):
                    continue
                if str(binding.get("binding_kind", "")).strip() != "shared_signal":
                    continue
                signal_name = str(binding.get("signal_name", "")).strip()
                signal_key = canonicalize_signal_name(
                    binding.get("canonical_signal_key")
                    or binding.get("signal_key")
                    or signal_name
                )
                if not signal_name or not signal_key:
                    continue
                direction = str(binding.get("direction", "")).strip()
                semantic_role = "shared_input" if direction == "input" else "shared_output"
                entry = ensure_entry(signal_name, signal_key, semantic_role)
                if not entry:
                    continue
                if direction == "input":
                    if subsystem_id not in entry["consumers"]:
                        entry["consumers"].append(subsystem_id)
                elif direction == "output":
                    entry["signal_name"] = signal_name or entry["signal_name"]
                    if subsystem_id not in entry["candidate_exporters"]:
                        entry["candidate_exporters"].append(subsystem_id)

        registry: List[Dict[str, Any]] = []
        for signal_key in sorted(registry_by_key):
            entry = registry_by_key[signal_key]
            exporters = list(entry.get("candidate_exporters", []) or [])
            consumers = list(entry.get("consumers", []) or [])
            resolution_evidence: List[str] = []
            if consumers:
                resolution_evidence.append(f"consumers={', '.join(sorted(consumers))}")
            if exporters:
                resolution_evidence.append(f"exporters={', '.join(sorted(exporters))}")
            if len(exporters) == 1:
                entry["owner_subsystem_id"] = exporters[0]
                entry["required_exporter_count"] = 1
                entry["candidate_exporters"] = sorted(exporters)
                entry["resolution_status"] = "resolved"
                resolution_evidence.append(f"owner={exporters[0]}")
                entry["source_reason"] = entry.get("source_reason") or "Single exporting subsystem detected from requirement projection."
            elif len(exporters) > 1:
                entry["owner_subsystem_id"] = ""
                entry["required_exporter_count"] = 1
                entry["candidate_exporters"] = sorted(exporters)
                entry["resolution_status"] = "ambiguous"
                resolution_evidence.append("multiple exporter candidates detected")
                entry["source_reason"] = "Multiple exporter candidates detected; planner must disambiguate ownership."
                warnings.append(
                    f"共享信号 {entry['signal_name']} 存在多个候选导出方: {', '.join(sorted(exporters))}。"
                )
            elif consumers:
                entry["required_exporter_count"] = 1
                entry["candidate_exporters"] = []
                entry["resolution_status"] = "missing_exporter"
                resolution_evidence.append("no exporter candidate detected")
                entry["source_reason"] = "Consumers detected but no exporter projected; planner expects a real subsystem exporter."
                warnings.append(
                    f"共享信号 {entry['signal_name']} 目前只有消费者 {', '.join(sorted(consumers))}，缺少明确导出方。"
                )
            else:
                entry["candidate_exporters"] = []
                entry["resolution_status"] = "missing_exporter"
                resolution_evidence.append("shared signal projected without exporter/consumer evidence")
            entry["resolution_evidence"] = resolution_evidence
            registry.append(entry)

        return registry, warnings

    @staticmethod
    def _propagate_shared_signal_resolution(
        subsystem_descriptors: List[Dict[str, Any]],
        shared_signal_registry: List[Dict[str, Any]],
    ) -> None:
        registry_by_key = {
            canonicalize_signal_name(
                item.get("canonical_signal_key")
                or item.get("signal_key")
                or item.get("signal_name")
            ): item
            for item in shared_signal_registry
            if isinstance(item, dict)
        }
        for descriptor in subsystem_descriptors:
            for binding in descriptor.get("interface_bindings", []) or []:
                if not isinstance(binding, dict):
                    continue
                if str(binding.get("binding_kind", "")).strip() != "shared_signal":
                    continue
                signal_key = canonicalize_signal_name(
                    binding.get("canonical_signal_key")
                    or binding.get("signal_key")
                    or binding.get("signal_name")
                )
                registry_entry = registry_by_key.get(signal_key, {})
                if not registry_entry:
                    continue
                binding["owner_subsystem_id"] = str(registry_entry.get("owner_subsystem_id", "")).strip()
                binding["candidate_exporters"] = list(registry_entry.get("candidate_exporters", []) or [])
                binding["resolution_status"] = str(registry_entry.get("resolution_status", "")).strip()
                binding["resolution_evidence"] = list(registry_entry.get("resolution_evidence", []) or [])

    def _build_pages(
        self,
        requirement_spec: Dict[str, Any],
        selected_pattern: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        pages: List[Dict[str, Any]] = []
        required_pages = requirement_spec.get("required_pages", []) or []
        required_labels = {str(label).strip() for label in required_pages if str(label).strip()}
        subsystem_types = {
            str(item.get("subsystem_type", "")).strip()
            for item in requirement_spec.get("subsystems", []) or []
            if isinstance(item, dict)
        }

        def add_page(label: str, kind: str, source: str, page_key: str = "") -> None:
            resolved_page_key = str(page_key).strip() or make_page_key(label)
            page_id = f"page_{resolved_page_key}"
            if any(page.get("page_id") == page_id for page in pages):
                return
            pages.append(
                {
                    "page_id": page_id,
                    "label": label,
                    "kind": kind or make_page_key(label),
                    "order": len(pages),
                    "source": source,
                }
            )

        for page in selected_pattern.get("required_pages", []) or []:
            label = str(page.get("label") or page.get("page_key") or "").strip()
            if label:
                add_page(
                    label,
                    str(page.get("kind", "")).strip(),
                    "system_pattern.required",
                    page_key=str(page.get("page_key", "")).strip(),
                )

        for page in selected_pattern.get("optional_pages", []) or []:
            label = str(page.get("label") or page.get("page_key") or "").strip()
            page_key = str(page.get("page_key", "")).strip()
            if not label:
                continue
            if label in required_labels:
                add_page(
                    label,
                    str(page.get("kind", "")).strip(),
                    "system_pattern.optional",
                    page_key=page_key,
                )
                continue
            if page_key == "exhaust_fan" and "exhaust_fan_control" in subsystem_types:
                add_page(
                    label,
                    str(page.get("kind", "")).strip(),
                    "system_pattern.optional",
                    page_key=page_key,
                )
            if page_key == "dx_fault" and "dx_control" in subsystem_types:
                add_page(
                    label,
                    str(page.get("kind", "")).strip(),
                    "system_pattern.optional",
                    page_key=page_key,
                )

        for label in required_pages:
            label = str(label).strip()
            if label:
                add_page(label, make_page_key(label), "requirement_spec")

        if not pages:
            add_page("控制", "control", "fallback")
        return pages

    @staticmethod
    def _fallback_subsystems(requirement_spec: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [
            {
                "subsystem_id": "main_control",
                "subsystem_type": "generic_control",
                "goal": str(requirement_spec.get("scenario_summary", "")).strip() or "通用控制逻辑",
                "page_hint": "控制",
                "priority": 1,
                "preferred_templates": [],
                "imports": list((requirement_spec.get("signals", {}) or {}).get("inputs", []) or []),
                "exports": list((requirement_spec.get("signals", {}) or {}).get("outputs", []) or []),
                "reasoning": "Fallback subsystem because requirement_spec.subsystems is empty.",
            }
        ]

    def plan(
        self,
        requirement_spec: Dict[str, Any],
        retrieval_bundle: Dict[str, Any],
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        decomposition_result = empty_decomposition_result()
        architecture_plan = empty_architecture_plan()

        selected_pattern, pattern_score_cards = self._select_system_pattern(requirement_spec, retrieval_bundle)
        subflow_templates = get_bundle_subflow_templates(retrieval_bundle)
        style_guides = get_bundle_style_guides(retrieval_bundle)
        pages = self._build_pages(requirement_spec, selected_pattern)
        subsystem_descriptors: List[Dict[str, Any]] = []
        subsystem_slots: List[Dict[str, Any]] = []
        template_needs: List[Dict[str, Any]] = []
        planning_order: List[str] = []
        explicit_import_keys: set[str] = set()
        explicit_export_keys: set[str] = set()

        raw_subsystems = requirement_spec.get("subsystems", []) or []
        if not raw_subsystems:
            raw_subsystems = self._fallback_subsystems(requirement_spec)
            architecture_plan["warnings"].append("requirement_spec.subsystems 为空，已退化为单一 generic_control 子系统。")
            decomposition_result["warnings"].append("requirement_spec.subsystems 为空，已退化为单一 generic_control 子系统。")

        for subsystem in raw_subsystems:
            if not isinstance(subsystem, dict):
                continue
            explicit_import_keys.update(
                canonicalize_signal_name(signal_name)
                for signal_name in subsystem.get("imports", []) or []
                if canonicalize_signal_name(signal_name)
            )
            explicit_export_keys.update(
                canonicalize_signal_name(signal_name)
                for signal_name in subsystem.get("exports", []) or []
                if canonicalize_signal_name(signal_name)
            )
        projected_shared_signal_keys = (explicit_import_keys & explicit_export_keys) | set(KNOWN_SHARED_SIGNAL_KEYS)

        for index, subsystem in enumerate(raw_subsystems, start=1):
            if not isinstance(subsystem, dict):
                continue
            subsystem_id = str(subsystem.get("subsystem_id", "")).strip() or f"subsystem_{index}"
            subsystem_type = str(subsystem.get("subsystem_type", "")).strip() or "generic_control"
            page_label = self._pick_page_label(subsystem_type, subsystem, pages)
            page_id = make_page_id(page_label)
            template_score_cards = self._rank_template_candidates(subsystem, subflow_templates, requirement_spec, page_label)
            preferred_template_ids = [
                str(item.get("template_id", "")).strip()
                for item in template_score_cards
                if int(item.get("score", 0) or 0) > 0 and str(item.get("template_id", "")).strip()
            ]
            implementation_preference = "reuse_template" if preferred_template_ids else "atomic_assembly"
            winning_template_card = template_score_cards[0] if preferred_template_ids and template_score_cards else {}
            selection_reason = (
                f"Selected template {winning_template_card.get('template_id')} with score={winning_template_card.get('score')}."
                f" Reasons: {'; '.join(winning_template_card.get('reasons', []) or [])}"
                if winning_template_card
                else "No qualified reusable template matched current subsystem context."
            )
            degrade_reason = (
                "No qualified reusable template matched current subsystem context; fallback to atomic_assembly."
                if not preferred_template_ids
                else ""
            )

            template_doc = next(
                (item for item in subflow_templates if item.get("template_id") == preferred_template_ids[0]),
                {},
            ) if preferred_template_ids else {}
            interface_bindings = self._build_interface_bindings(
                requirement_spec,
                subsystem,
                template_doc,
                projected_shared_signal_keys,
                explicit_import_keys,
            )
            imports = [
                str(binding.get("signal_name", "")).strip()
                for binding in interface_bindings
                if str(binding.get("direction", "")).strip() == "input" and str(binding.get("signal_name", "")).strip()
            ]
            exports = [
                str(binding.get("signal_name", "")).strip()
                for binding in interface_bindings
                if str(binding.get("direction", "")).strip() == "output" and str(binding.get("signal_name", "")).strip()
            ]

            subsystem_descriptors.append(
                {
                    "subsystem_id": subsystem_id,
                    "subsystem_type": subsystem_type,
                    "page_id": page_id,
                    "goal": str(subsystem.get("goal", "")).strip(),
                    "implementation_preference": implementation_preference,
                    "interface_bindings": interface_bindings,
                    "imports": imports,
                    "exports": exports,
                    "priority": int(subsystem.get("priority", index) or index),
                    "reasoning": str(subsystem.get("reasoning", "")).strip() or "Projected from requirement_spec.",
                }
            )
            subsystem_slots.append(
                {
                    "subsystem_id": subsystem_id,
                    "page_id": page_id,
                    "preferred_implementation": implementation_preference,
                    "preferred_template_ids": preferred_template_ids,
                    "score_breakdown": template_score_cards[:3],
                    "selection_reason": selection_reason,
                    "degrade_reason": degrade_reason,
                    "fallback_mode": "atomic_assembly",
                    "priority": int(subsystem.get("priority", index) or index),
                    "reasoning": f"{implementation_preference} based on subflow template coverage.",
                }
            )
            template_needs.append(
                {
                    "subsystem_id": subsystem_id,
                    "preferred_template_ids": preferred_template_ids,
                    "implementation_preference": implementation_preference,
                }
            )
            planning_order.append(subsystem_id)

        shared_signal_registry, shared_signal_warnings = self._build_shared_signal_registry(
            requirement_spec,
            subsystem_descriptors,
            planning_order,
        )
        self._propagate_shared_signal_resolution(subsystem_descriptors, shared_signal_registry)

        pattern_bindings: List[Dict[str, Any]] = []
        if selected_pattern:
            selected_pattern_id = str(selected_pattern.get("pattern_id", "")).strip()
            selected_card = next(
                (item for item in pattern_score_cards if item.get("pattern_id") == selected_pattern_id),
                {},
            )
            pattern_bindings.append(
                {
                    "pattern_id": selected_pattern_id,
                    "reasoning": "Use scored system pattern selection to seed pages and shared-signal constraints.",
                    "score": int(selected_card.get("score", 0) or 0),
                    "score_reasons": list(selected_card.get("reasons", []) or []),
                    "score_breakdown": dict(selected_card.get("score_breakdown", {}) or {}),
                    "applied_scope": {
                        "pages": [page.get("page_id") for page in pages],
                        "required_page_count": len(selected_pattern.get("required_pages", []) or []),
                    },
                }
            )

        naming_strategy = {
            "signal_prefix": str(requirement_spec.get("system_type", "system")).strip().lower() or "system",
            "page_id_format": "page_<page_key>",
        }
        layout_strategy = {
            "page_order": [page.get("page_id") for page in pages],
            "subsystem_spacing_y": 360,
            "page_spacing_x": 1600,
        }
        for style_guide in style_guides:
            if isinstance(style_guide, dict):
                naming_strategy.update(style_guide.get("naming", {}) or {})
                layout_strategy.update(style_guide.get("layout", {}) or {})

        architecture_plan.update(
            {
                "goal": str(requirement_spec.get("scenario_summary", "")).strip() or "Phase 3 architecture planning",
                "pages": pages,
                "subsystem_slots": subsystem_slots,
                "shared_signal_registry": shared_signal_registry,
                "global_constraints": [
                    {
                        "constraint_id": f"mode::{mode}",
                        "type": "global_mode",
                        "value": mode,
                        "source": "requirement_spec.global_modes",
                    }
                    for mode in requirement_spec.get("global_modes", []) or []
                ] + [
                    {
                        "constraint_id": f"shared_signal::{item.get('signal_key')}",
                        "type": "shared_signal_ownership",
                        "value": item.get("owner_subsystem_id", ""),
                        "source": item.get("source_reason", "shared_signal_registry"),
                    }
                    for item in shared_signal_registry
                ],
                "naming_strategy": naming_strategy,
                "layout_strategy": layout_strategy,
                "pattern_bindings": pattern_bindings,
                "warnings": list(requirement_spec.get("warnings", []) or []) + shared_signal_warnings,
            }
        )
        decomposition_result.update(
            {
                "pages": pages,
                "subsystem_descriptors": subsystem_descriptors,
                "shared_signal_registry": shared_signal_registry,
                "template_needs": template_needs,
                "planning_order": planning_order,
                "warnings": list(requirement_spec.get("warnings", []) or []) + shared_signal_warnings,
            }
        )

        if config.DEBUG:
            print("[ArchitecturePlanner] completed")
            print(f"   pages={len(pages)} subsystems={len(subsystem_descriptors)}")

        return decomposition_result, architecture_plan

    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        requirement_spec = state.get("requirement_spec", {}) or {}
        retrieval_bundle = state.get("retrieval_bundle", {}) or {}
        decomposition_result, architecture_plan = self.plan(requirement_spec, retrieval_bundle)
        state["decomposition_result"] = decomposition_result
        state["architecture_plan"] = architecture_plan
        state["current_step"] = "architecture_planned"
        return state
