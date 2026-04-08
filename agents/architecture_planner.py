"""Phase 3 architecture planner."""
from __future__ import annotations

from typing import Any, Dict, List

import config
from utils.console_utils import safe_print as print
from utils.phase3_adapters import make_page_id, make_page_key, normalize_signal_name
from utils.phase3_contracts import empty_architecture_plan, empty_decomposition_result
from utils.retrieval_bundle_utils import get_style_guides, get_subflow_templates, get_system_patterns


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


class ArchitecturePlanner:
    """Build a deterministic system skeleton from requirement_spec and retrieval assets."""

    def __init__(self):
        if config.DEBUG:
            print("[ArchitecturePlanner] initialized")

    @staticmethod
    def _select_system_pattern(retrieval_bundle: Dict[str, Any]) -> Dict[str, Any]:
        patterns = get_system_patterns(retrieval_bundle)
        metadata = retrieval_bundle.get("metadata", {}) if isinstance(retrieval_bundle, dict) else {}
        selected_pattern_id = ""
        if isinstance(metadata, dict):
            selected_pattern_id = str(metadata.get("selected_case_pattern_id", "")).strip()

        for pattern in patterns:
            if str(pattern.get("pattern_id", "")).strip() == selected_pattern_id:
                return pattern
        return patterns[0] if patterns else {}

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
        ports_definition = template_doc.get("ports_definition", {}) if isinstance(template_doc, dict) else {}
        if not isinstance(ports_definition, dict):
            return []
        port_items = ports_definition.get(direction, [])
        signals: List[str] = []
        for item in port_items if isinstance(port_items, list) else []:
            label = str(item.get("label") or item.get("name") or "").strip()
            if label:
                signals.append(label)
        return signals

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
            score = sum(1 for keyword in keywords if keyword.lower() in searchable or keyword.lower() in goal_text)
            if score > 0:
                scored.append((score, template_id))

        ordered: List[str] = []
        seen = set()
        for _, template_id in sorted(scored, key=lambda item: (-item[0], item[1])):
            if template_id not in seen:
                ordered.append(template_id)
                seen.add(template_id)
        return ordered

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

        selected_pattern = self._select_system_pattern(retrieval_bundle)
        subflow_templates = get_subflow_templates(retrieval_bundle)
        style_guides = get_style_guides(retrieval_bundle)
        pages = self._build_pages(requirement_spec, selected_pattern)
        subsystem_descriptors: List[Dict[str, Any]] = []
        subsystem_slots: List[Dict[str, Any]] = []
        template_needs: List[Dict[str, Any]] = []
        planning_order: List[str] = []

        raw_subsystems = requirement_spec.get("subsystems", []) or []
        if not raw_subsystems:
            raw_subsystems = self._fallback_subsystems(requirement_spec)
            architecture_plan["warnings"].append("requirement_spec.subsystems 为空，已退化为单一 generic_control 子系统。")
            decomposition_result["warnings"].append("requirement_spec.subsystems 为空，已退化为单一 generic_control 子系统。")

        for index, subsystem in enumerate(raw_subsystems, start=1):
            if not isinstance(subsystem, dict):
                continue
            subsystem_id = str(subsystem.get("subsystem_id", "")).strip() or f"subsystem_{index}"
            subsystem_type = str(subsystem.get("subsystem_type", "")).strip() or "generic_control"
            preferred_template_ids = self._match_template_ids(subsystem, subflow_templates)
            page_label = self._pick_page_label(subsystem_type, subsystem, pages)
            page_id = make_page_id(page_label)
            implementation_preference = "reuse_template" if preferred_template_ids else "atomic_assembly"

            template_doc = next(
                (item for item in subflow_templates if item.get("template_id") == preferred_template_ids[0]),
                {},
            ) if preferred_template_ids else {}
            imports = subsystem.get("imports", []) or self._extract_template_signals(template_doc, "inputs")
            exports = subsystem.get("exports", []) or self._extract_template_signals(template_doc, "outputs")

            subsystem_descriptors.append(
                {
                    "subsystem_id": subsystem_id,
                    "subsystem_type": subsystem_type,
                    "page_id": page_id,
                    "goal": str(subsystem.get("goal", "")).strip(),
                    "implementation_preference": implementation_preference,
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

        shared_signal_registry: List[Dict[str, Any]] = []
        for mode in requirement_spec.get("global_modes", []) or []:
            signal_name = normalize_signal_name(mode)
            if signal_name:
                shared_signal_registry.append(
                    {
                        "signal_name": signal_name,
                        "semantic_role": "global_mode",
                        "shared_by": list(planning_order),
                    }
                )

        pattern_bindings: List[Dict[str, Any]] = []
        if selected_pattern:
            pattern_bindings.append(
                {
                    "pattern_id": str(selected_pattern.get("pattern_id", "")).strip(),
                    "reasoning": "Use retrieved system pattern to seed pages and global structure.",
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
                "global_constraints": [
                    {
                        "constraint_id": f"mode::{mode}",
                        "type": "global_mode",
                        "value": mode,
                        "source": "requirement_spec.global_modes",
                    }
                    for mode in requirement_spec.get("global_modes", []) or []
                ],
                "naming_strategy": naming_strategy,
                "layout_strategy": layout_strategy,
                "pattern_bindings": pattern_bindings,
                "warnings": list(requirement_spec.get("warnings", []) or []),
            }
        )
        decomposition_result.update(
            {
                "pages": pages,
                "subsystem_descriptors": subsystem_descriptors,
                "shared_signal_registry": shared_signal_registry,
                "template_needs": template_needs,
                "planning_order": planning_order,
                "warnings": list(requirement_spec.get("warnings", []) or []),
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
