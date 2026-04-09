"""Phase 3 subsystem planner."""
from __future__ import annotations

from typing import Any, Dict, List

import config
from utils.console_utils import safe_print as print
from utils.phase3_contracts import empty_subsystem_plan
from utils.retrieval_bundle_utils import get_atomic_modules, build_compilable_doc_map
from .coding_utils import resolve_input_count, resolve_output_count


class SubsystemPlanner:
    """Build subsystem-local IR in a deterministic, sequential fashion."""

    def __init__(self):
        if config.DEBUG:
            print("[SubsystemPlanner] initialized")

    @staticmethod
    def _normalize_template(template_raw: Any) -> Dict[str, Any]:
        if isinstance(template_raw, list):
            if template_raw and isinstance(template_raw[0], dict):
                return dict(template_raw[0])
            return {}
        if isinstance(template_raw, dict):
            return dict(template_raw)
        return {}

    @staticmethod
    def _resolve_counts(module_doc: Dict[str, Any], parameters: Dict[str, Any]) -> tuple[int, int]:
        template_json = module_doc.get("template_json", {}) if isinstance(module_doc, dict) else {}
        template = SubsystemPlanner._normalize_template(template_json)
        compile_hints = module_doc.get("compile_hints", {}) if isinstance(module_doc, dict) else {}
        if template.get("type") == "subflow":
            return (
                int(compile_hints.get("input_count", len((module_doc.get("ports_definition", {}) or {}).get("inputs", []))) or 0),
                int(compile_hints.get("output_count", len((module_doc.get("ports_definition", {}) or {}).get("outputs", []))) or 0),
            )

        input_count = resolve_input_count(template.get("inputs", 0), parameters, module_doc)
        output_count = resolve_output_count(template.get("outputs", 0), parameters, module_doc)
        return int(input_count or 0), int(output_count or 0)

    @staticmethod
    def _select_template_doc(slot: Dict[str, Any], doc_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        for template_id in slot.get("preferred_template_ids", []) or []:
            if template_id in doc_map:
                return doc_map[template_id]
        return {}

    @staticmethod
    def _signal_names(values: Any, default_prefix: str, count: int) -> List[str]:
        if isinstance(values, list):
            names = [str(value).strip() for value in values if str(value).strip()]
            if names:
                return names
        return [f"{default_prefix}_{index + 1}" for index in range(max(0, count))]

    def _select_atomic_primary_doc(
        self,
        descriptor: Dict[str, Any],
        atomic_modules: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        subsystem_text = " ".join(
            str(descriptor.get(key, "")).lower()
            for key in ("subsystem_type", "goal", "reasoning")
        )
        best_doc: Dict[str, Any] = {}
        best_score = -1

        for doc in atomic_modules:
            searchable = " ".join(
                str(doc.get(key, "")).lower()
                for key in ("module_type", "name", "description", "category")
            )
            score = 0
            for token in subsystem_text.split():
                if token and token in searchable:
                    score += 1
            input_count, output_count = self._resolve_counts(doc, {})
            if output_count > 0:
                score += 1
            if input_count > 0:
                score += 2
            module_type = str(doc.get("module_type", "")).lower()
            if any(token in module_type for token in ("const", "quote", "input")):
                score -= 1
            if score > best_score:
                best_score = score
                best_doc = doc

        return best_doc or (atomic_modules[0] if atomic_modules else {})

    def _select_source_doc(self, atomic_modules: List[Dict[str, Any]]) -> Dict[str, Any]:
        preferred = ("constinput", "swinput", "variable", "physicalinput", "modbus", "mqtt")
        best_doc: Dict[str, Any] = {}
        best_score = -1
        for doc in atomic_modules:
            input_count, output_count = self._resolve_counts(doc, {})
            if input_count != 0 or output_count <= 0:
                continue
            module_type = str(doc.get("module_type", "")).lower()
            score = 1
            for index, token in enumerate(preferred):
                if token in module_type:
                    score = 100 - index
                    break
            if score > best_score:
                best_score = score
                best_doc = doc
        return best_doc

    @staticmethod
    def _default_parameters(module_doc: Dict[str, Any], name: str, desired_inputs: int) -> Dict[str, Any]:
        parameters: Dict[str, Any] = {}
        params_schema = module_doc.get("parameters_schema", {}) if isinstance(module_doc, dict) else {}
        if not isinstance(params_schema, dict):
            params_schema = {}

        if "name" in params_schema:
            parameters["name"] = name
        if "fixedValue" in params_schema:
            parameters["fixedValue"] = 0
        for key in ("inputCount", "inputs", "inputsCount"):
            if key in params_schema:
                parameters[key] = max(1, desired_inputs)
        if "channels" in params_schema and desired_inputs > 1:
            parameters["channels"] = max(1, desired_inputs - 1)
        return parameters

    @staticmethod
    def _build_signal_bindings(
        signal_names: List[str],
        node_logic_id: str,
        page_id: str,
        count: int,
        semantic_role: str,
    ) -> List[Dict[str, Any]]:
        bindings: List[Dict[str, Any]] = []
        for port_index in range(max(count, len(signal_names))):
            signal_name = signal_names[port_index] if port_index < len(signal_names) else f"{semantic_role}_{port_index + 1}"
            bindings.append(
                {
                    "signal_name": signal_name,
                    "node_logic_id": node_logic_id,
                    "port_index": port_index,
                    "page_id": page_id,
                    "semantic_role": semantic_role,
                    "required": True,
                    "reasoning": "Projected from subsystem interface.",
                }
            )
        return bindings

    def _plan_template_reuse(
        self,
        descriptor: Dict[str, Any],
        slot: Dict[str, Any],
        template_doc: Dict[str, Any],
    ) -> Dict[str, Any]:
        subsystem_id = str(descriptor.get("subsystem_id", "")).strip()
        page_id = str(descriptor.get("page_id", "")).strip()
        template_id = str(template_doc.get("template_id") or template_doc.get("module_type") or "").strip()
        main_logic_id = f"{subsystem_id}_main"
        input_count, output_count = self._resolve_counts(template_doc, {})
        import_names = self._signal_names(descriptor.get("imports", []), f"{subsystem_id}_input", input_count)
        export_names = self._signal_names(descriptor.get("exports", []), f"{subsystem_id}_output", output_count)

        subsystem_plan = empty_subsystem_plan(subsystem_id=subsystem_id, page_id=page_id)
        subsystem_plan.update(
            {
                "implementation_mode": "reuse_template",
                "template_binding": {
                    "template_id": template_id,
                    "reasoning": "Matched architecture preferred_template_ids against retrieval bundle.",
                },
                "node_instances": [
                    {
                        "logic_id": main_logic_id,
                        "module_type": template_id,
                        "page_id": page_id,
                        "template_id": template_id,
                        "parameters": {"name": str(template_doc.get("template_name") or descriptor.get("goal") or subsystem_id)},
                        "input_count": input_count,
                        "output_count": output_count,
                        "position": {"x": 0, "y": 0},
                        "reasoning": f"Reuse template {template_id} for subsystem {subsystem_id}.",
                    }
                ],
                "edges": [],
                "imported_signals": self._build_signal_bindings(import_names, main_logic_id, page_id, input_count, "import"),
                "exported_signals": self._build_signal_bindings(export_names, main_logic_id, page_id, output_count, "export"),
                "constraints": [
                    {
                        "constraint_id": f"{subsystem_id}::implementation",
                        "value": "reuse_template",
                        "source": "architecture_plan.subsystem_slots",
                    }
                ],
                "reasoning": str(slot.get("reasoning", "")).strip() or "Template reuse path selected.",
            }
        )
        return subsystem_plan

    def _plan_atomic_fallback(
        self,
        descriptor: Dict[str, Any],
        slot: Dict[str, Any],
        atomic_modules: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        subsystem_id = str(descriptor.get("subsystem_id", "")).strip()
        page_id = str(descriptor.get("page_id", "")).strip()
        subsystem_plan = empty_subsystem_plan(subsystem_id=subsystem_id, page_id=page_id)
        primary_doc = self._select_atomic_primary_doc(descriptor, atomic_modules)
        if not primary_doc:
            subsystem_plan.update(
                {
                    "implementation_mode": "atomic_assembly",
                    "reasoning": "No atomic module candidates available.",
                    "unresolved_items": [
                        {
                            "type": "missing_atomic_candidates",
                            "severity": "error",
                            "subsystem_id": subsystem_id,
                            "message": "No atomic_modules available for subsystem fallback.",
                            "suggested_fix": "补齐 atomic_modules，或为该子系统提供可复用的 subflow template。",
                        }
                    ],
                }
            )
            return subsystem_plan

        import_seed = descriptor.get("imports", []) or []
        desired_inputs = len(import_seed) or 1
        primary_logic_id = f"{subsystem_id}_main"
        primary_parameters = self._default_parameters(primary_doc, str(descriptor.get("goal") or subsystem_id), desired_inputs)
        primary_input_count, primary_output_count = self._resolve_counts(primary_doc, primary_parameters)
        import_names = self._signal_names(import_seed, f"{subsystem_id}_input", primary_input_count)
        export_names = self._signal_names(descriptor.get("exports", []), f"{subsystem_id}_output", max(1, primary_output_count))

        node_instances: List[Dict[str, Any]] = [
            {
                "logic_id": primary_logic_id,
                "module_type": str(primary_doc.get("module_type", "")).strip(),
                "page_id": page_id,
                "template_id": None,
                "parameters": primary_parameters,
                "input_count": primary_input_count,
                "output_count": primary_output_count,
                "position": {"x": 260, "y": 0},
                "reasoning": "Atomic fallback primary node.",
            }
        ]
        edges: List[Dict[str, Any]] = []
        unresolved_items: List[Dict[str, Any]] = []

        source_doc = self._select_source_doc(atomic_modules)
        if primary_input_count > 0 and not source_doc:
            unresolved_items.append(
                {
                    "type": "missing_placeholder_source",
                    "severity": "error",
                    "subsystem_id": subsystem_id,
                    "message": "No zero-input atomic module available to satisfy fallback inputs.",
                    "suggested_fix": "补齐可作为输入占位源的零输入原子模块，或为该子系统提供完整模板。",
                }
            )

        for port_index in range(primary_input_count):
            if not source_doc:
                break
            signal_name = import_names[port_index] if port_index < len(import_names) else f"{subsystem_id}_input_{port_index + 1}"
            source_logic_id = f"{subsystem_id}_src_{port_index + 1}"
            source_parameters = self._default_parameters(source_doc, signal_name, 0)
            source_input_count, source_output_count = self._resolve_counts(source_doc, source_parameters)
            node_instances.append(
                {
                    "logic_id": source_logic_id,
                    "module_type": str(source_doc.get("module_type", "")).strip(),
                    "page_id": page_id,
                    "template_id": None,
                    "parameters": source_parameters,
                    "input_count": source_input_count,
                    "output_count": max(1, source_output_count),
                    "position": {"x": 0, "y": port_index * 120},
                    "reasoning": "Synthetic local source for atomic fallback input.",
                }
            )
            edges.append(
                {
                    "from_node": source_logic_id,
                    "from_port": 0,
                    "to_node": primary_logic_id,
                    "to_port": port_index,
                    "signal_name": signal_name,
                }
            )

        subsystem_plan.update(
            {
                "implementation_mode": "atomic_assembly",
                "template_binding": {
                    "template_id": "",
                    "reasoning": "Preferred templates unavailable; fell back to atomic modules.",
                },
                "node_instances": node_instances,
                "edges": edges,
                "imported_signals": self._build_signal_bindings(import_names, primary_logic_id, page_id, primary_input_count, "import"),
                "exported_signals": self._build_signal_bindings(export_names, primary_logic_id, page_id, max(1, primary_output_count), "export"),
                "constraints": [
                    {
                        "constraint_id": f"{subsystem_id}::implementation",
                        "value": "atomic_assembly",
                        "source": "architecture_plan.subsystem_slots.fallback_mode",
                    }
                ],
                "unresolved_items": unresolved_items,
                "reasoning": str(slot.get("reasoning", "")).strip() or "Atomic fallback path selected.",
            }
        )
        return subsystem_plan

    def plan(
        self,
        requirement_spec: Dict[str, Any],
        decomposition_result: Dict[str, Any],
        architecture_plan: Dict[str, Any],
        retrieval_bundle: Dict[str, Any],
    ) -> Dict[str, Dict[str, Any]]:
        del requirement_spec
        doc_map = build_compilable_doc_map(retrieval_bundle)
        atomic_modules = get_atomic_modules(retrieval_bundle)
        subsystem_descriptors = {
            str(item.get("subsystem_id", "")).strip(): item
            for item in decomposition_result.get("subsystem_descriptors", []) or []
            if isinstance(item, dict) and str(item.get("subsystem_id", "")).strip()
        }
        subsystem_slots = {
            str(item.get("subsystem_id", "")).strip(): item
            for item in architecture_plan.get("subsystem_slots", []) or []
            if isinstance(item, dict) and str(item.get("subsystem_id", "")).strip()
        }
        planning_order = [
            str(item).strip()
            for item in decomposition_result.get("planning_order", []) or []
            if str(item).strip()
        ]
        if not planning_order:
            planning_order = list(subsystem_descriptors.keys())

        subsystem_plan_map: Dict[str, Dict[str, Any]] = {}
        for subsystem_id in planning_order:
            descriptor = subsystem_descriptors.get(subsystem_id, {})
            slot = subsystem_slots.get(subsystem_id, {})
            template_doc = self._select_template_doc(slot, doc_map)
            if template_doc:
                subsystem_plan = self._plan_template_reuse(descriptor, slot, template_doc)
            else:
                subsystem_plan = self._plan_atomic_fallback(descriptor, slot, atomic_modules)
            subsystem_plan_map[subsystem_id] = subsystem_plan

        if config.DEBUG:
            print("[SubsystemPlanner] completed")
            print(f"   subsystems={len(subsystem_plan_map)}")

        return subsystem_plan_map

    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        subsystem_plan_map = self.plan(
            state.get("requirement_spec", {}) or {},
            state.get("decomposition_result", {}) or {},
            state.get("architecture_plan", {}) or {},
            state.get("retrieval_bundle", {}) or {},
        )
        state["subsystem_plan_map"] = subsystem_plan_map
        state["current_step"] = "subsystem_planned"
        return state
