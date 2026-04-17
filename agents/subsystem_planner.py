"""Phase 3 subsystem planner."""
from __future__ import annotations

from typing import Any, Dict, List

import config
from utils.console_utils import safe_print as print
from utils.phase3_adapters import normalize_signal_name
from utils.phase3_contracts import empty_subsystem_plan
from utils.retrieval_bundle_utils import get_atomic_modules, build_compilable_doc_map
from utils.signal_semantics import canonicalize_signal_name
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
        interface_bindings: List[Dict[str, Any]],
        node_logic_id: str,
        page_id: str,
        semantic_role: str,
    ) -> List[Dict[str, Any]]:
        bindings: List[Dict[str, Any]] = []
        for fallback_index, binding in enumerate(interface_bindings):
            signal_name = str(binding.get("signal_name", "")).strip()
            if not signal_name:
                continue
            bindings.append(
                {
                    "signal_name": signal_name,
                    "signal_key": str(binding.get("signal_key", "")).strip() or normalize_signal_name(signal_name),
                    "canonical_signal_key": str(binding.get("canonical_signal_key", "")).strip() or normalize_signal_name(signal_name),
                    "node_logic_id": node_logic_id,
                    "port_index": int(binding.get("port_index", fallback_index) or fallback_index),
                    "page_id": page_id,
                    "binding_kind": str(binding.get("binding_kind", "")).strip(),
                    "allowed_external": bool(binding.get("allowed_external", False)),
                    "owner_subsystem_id": str(binding.get("owner_subsystem_id", "")).strip(),
                    "resolution_status": str(binding.get("resolution_status", "")).strip(),
                    "candidate_exporters": list(binding.get("candidate_exporters", []) or []),
                    "resolution_evidence": list(binding.get("resolution_evidence", []) or []),
                    "semantic_role": semantic_role,
                    "required": True,
                    "reasoning": "Projected from subsystem interface_bindings.",
                }
            )
        return bindings

    @staticmethod
    def _shared_signal_registry(
        requirement_spec: Dict[str, Any],
        decomposition_result: Dict[str, Any],
        architecture_plan: Dict[str, Any],
    ) -> Dict[str, Dict[str, Any]]:
        registry_items = (
            architecture_plan.get("shared_signal_registry", []) or []
            or decomposition_result.get("shared_signal_registry", []) or []
        )
        registry: Dict[str, Dict[str, Any]] = {}
        for item in registry_items:
            if not isinstance(item, dict):
                continue
            signal_key = normalize_signal_name(
                item.get("canonical_signal_key")
                or item.get("signal_key")
                or item.get("signal_name")
            )
            if signal_key:
                registry[signal_key] = dict(item)
        return registry

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

    def _descriptor_interface_bindings(
        self,
        descriptor: Dict[str, Any],
        shared_signal_registry: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        bindings = descriptor.get("interface_bindings", [])
        normalized_bindings: List[Dict[str, Any]] = []
        if isinstance(bindings, list):
            for binding in bindings:
                if not isinstance(binding, dict):
                    continue
                signal_name = str(binding.get("signal_name", "")).strip()
                direction = str(binding.get("direction", "")).strip()
                if not signal_name or direction not in {"input", "output"}:
                    continue
                canonical_signal_key = str(binding.get("canonical_signal_key", "")).strip() or canonicalize_signal_name(signal_name)
                signal_key = str(binding.get("signal_key", "")).strip() or normalize_signal_name(signal_name)
                registry_entry = shared_signal_registry.get(canonical_signal_key, {})
                normalized_bindings.append(
                    {
                        "signal_name": signal_name,
                        "signal_key": signal_key,
                        "canonical_signal_key": canonical_signal_key,
                        "direction": direction,
                        "binding_kind": str(binding.get("binding_kind", "")).strip()
                        or ("shared_signal" if canonical_signal_key in shared_signal_registry else ("external_input" if direction == "input" else "subsystem_output")),
                        "allowed_external": bool(
                            binding.get("allowed_external", False)
                            if "allowed_external" in binding
                            else (direction == "input" and canonical_signal_key not in shared_signal_registry)
                        ),
                        "owner_subsystem_id": str(binding.get("owner_subsystem_id", "")).strip()
                        or str(registry_entry.get("owner_subsystem_id", "")).strip(),
                        "resolution_status": str(binding.get("resolution_status", "")).strip()
                        or str(registry_entry.get("resolution_status", "")).strip(),
                        "candidate_exporters": list(
                            binding.get("candidate_exporters", [])
                            or registry_entry.get("candidate_exporters", [])
                            or registry_entry.get("exporter_candidates", [])
                            or []
                        ),
                        "resolution_evidence": list(
                            binding.get("resolution_evidence", [])
                            or registry_entry.get("resolution_evidence", [])
                            or []
                        ),
                        "port_index": int(binding.get("port_index", len(normalized_bindings)) or len(normalized_bindings)),
                        "evidence": list(binding.get("evidence", []) or []),
                        "confidence": float(binding.get("confidence", 0.0) or 0.0),
                    }
                )
        if normalized_bindings:
            return sorted(
                normalized_bindings,
                key=lambda item: (0 if item.get("direction") == "input" else 1, int(item.get("port_index", 0) or 0)),
            )

        fallback_bindings: List[Dict[str, Any]] = []
        for direction, signal_names, default_kind in (
            ("input", list(descriptor.get("imports", []) or []), "external_input"),
            ("output", list(descriptor.get("exports", []) or []), "subsystem_output"),
        ):
            for port_index, signal_name in enumerate(self._dedupe_signal_names(signal_names)):
                canonical_signal_key = canonicalize_signal_name(signal_name)
                registry_entry = shared_signal_registry.get(canonical_signal_key, {})
                binding_kind = "shared_signal" if registry_entry else default_kind
                fallback_bindings.append(
                    {
                        "signal_name": signal_name,
                        "signal_key": normalize_signal_name(signal_name),
                        "canonical_signal_key": canonical_signal_key,
                        "direction": direction,
                        "binding_kind": binding_kind,
                        "allowed_external": bool(registry_entry.get("allowed_external", direction == "input" and binding_kind != "shared_signal")),
                        "owner_subsystem_id": str(registry_entry.get("owner_subsystem_id", "")).strip(),
                        "resolution_status": str(registry_entry.get("resolution_status", "")).strip(),
                        "candidate_exporters": list(
                            registry_entry.get("candidate_exporters", [])
                            or registry_entry.get("exporter_candidates", [])
                            or []
                        ),
                        "resolution_evidence": list(registry_entry.get("resolution_evidence", []) or []),
                        "port_index": port_index,
                        "evidence": ["Synthesized from compat imports/exports."],
                        "confidence": 0.5,
                    }
                )
        return fallback_bindings

    @staticmethod
    def _bindings_for_direction(interface_bindings: List[Dict[str, Any]], direction: str) -> List[Dict[str, Any]]:
        return [
            binding
            for binding in sorted(interface_bindings, key=lambda item: int(item.get("port_index", 0) or 0))
            if str(binding.get("direction", "")).strip() == direction
        ]

    @staticmethod
    def _ensure_binding_count(
        interface_bindings: List[Dict[str, Any]],
        direction: str,
        default_prefix: str,
        count: int,
    ) -> List[Dict[str, Any]]:
        if count <= 0:
            return []
        ordered = list(interface_bindings[:count])
        for index in range(len(ordered), count):
            signal_name = f"{default_prefix}_{index + 1}"
            signal_key = normalize_signal_name(signal_name)
            ordered.append(
                {
                    "signal_name": signal_name,
                    "signal_key": signal_key,
                    "canonical_signal_key": signal_key,
                    "direction": direction,
                    "binding_kind": "external_input" if direction == "input" else "subsystem_output",
                    "allowed_external": direction == "input",
                    "owner_subsystem_id": "",
                    "port_index": index,
                    "evidence": ["Synthesized to satisfy fallback port count."],
                    "confidence": 0.4,
                }
            )
        return ordered

    def _analyze_template_interface(
        self,
        descriptor: Dict[str, Any],
        template_doc: Dict[str, Any],
        shared_signal_registry: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        subsystem_id = str(descriptor.get("subsystem_id", "")).strip()
        template_id = str(template_doc.get("template_id") or template_doc.get("module_type") or "").strip()
        input_count, output_count = self._resolve_counts(template_doc, {})
        interface_bindings = self._descriptor_interface_bindings(descriptor, shared_signal_registry)
        input_bindings = self._bindings_for_direction(interface_bindings, "input")
        output_bindings = self._bindings_for_direction(interface_bindings, "output")

        issues: List[Dict[str, Any]] = []
        if len(input_bindings) > input_count:
            issues.append(
                {
                    "type": "template_input_interface_mismatch",
                    "severity": "error",
                    "scope": "planning",
                    "subsystem_id": subsystem_id,
                    "message": (
                        f"Template {template_id} only exposes {input_count} inputs but planner projected "
                        f"{len(input_bindings)} imported signals."
                    ),
                    "suggested_fix": "更换更匹配的子流程模板，或在架构层减少该子系统的共享输入约束。",
                }
            )
        if len(output_bindings) > output_count:
            issues.append(
                {
                    "type": "template_output_interface_mismatch",
                    "severity": "error",
                    "scope": "planning",
                    "subsystem_id": subsystem_id,
                    "message": (
                        f"Template {template_id} only exposes {output_count} outputs but planner projected "
                        f"{len(output_bindings)} exported signals."
                    ),
                    "suggested_fix": "更换更匹配的子流程模板，或在架构层修正该子系统的导出信号归属。",
                }
            )

        return {
            "template_id": template_id,
            "input_count": input_count,
            "output_count": output_count,
            "interface_bindings": interface_bindings,
            "input_bindings": input_bindings,
            "output_bindings": output_bindings,
            "issues": issues,
        }

    def _plan_template_reuse(
        self,
        descriptor: Dict[str, Any],
        slot: Dict[str, Any],
        template_doc: Dict[str, Any],
        atomic_modules: List[Dict[str, Any]],
        shared_signal_registry: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        subsystem_id = str(descriptor.get("subsystem_id", "")).strip()
        page_id = str(descriptor.get("page_id", "")).strip()
        interface_analysis = self._analyze_template_interface(descriptor, template_doc, shared_signal_registry)
        template_id = str(interface_analysis.get("template_id", "")).strip()
        main_logic_id = f"{subsystem_id}_main"
        input_count = int(interface_analysis.get("input_count", 0) or 0)
        output_count = int(interface_analysis.get("output_count", 0) or 0)
        interface_bindings = list(interface_analysis.get("interface_bindings", []) or [])
        input_bindings = list(interface_analysis.get("input_bindings", []) or [])
        output_bindings = list(interface_analysis.get("output_bindings", []) or [])
        issues = list(interface_analysis.get("issues", []) or [])
        if issues:
            issue_types = [str(item.get("type", "")).strip() for item in issues if str(item.get("type", "")).strip()]
            degrade_reason = (
                f"Template {template_id} interface mismatch ({', '.join(issue_types)}); fallback to atomic_assembly. "
                + " ".join(str(item.get("message", "")).strip() for item in issues if str(item.get("message", "")).strip())
            ).strip()
            degraded_slot = dict(slot)
            degraded_slot["selection_reason"] = (
                str(slot.get("selection_reason", "")).strip()
                or f"Selected reusable template {template_id}."
            ) + f" Rejected due to interface mismatch; fallback to atomic_assembly."
            degraded_slot["degrade_reason"] = degrade_reason
            degraded_slot["reasoning"] = "Atomic fallback path selected after template interface mismatch."
            fallback_plan = self._plan_atomic_fallback(
                descriptor,
                degraded_slot,
                atomic_modules,
                shared_signal_registry,
            )
            template_binding = dict(fallback_plan.get("template_binding", {}) or {})
            template_binding.update(
                {
                    "template_id": template_id,
                    "reasoning": "Selected template rejected due to interface mismatch; fell back to atomic modules.",
                    "degraded": True,
                    "degrade_from": "reuse_template",
                    "degrade_reason": degrade_reason,
                    "degrade_issue_types": issue_types,
                    "score_breakdown": list(slot.get("score_breakdown", []) or []),
                }
            )
            fallback_plan["template_binding"] = template_binding
            fallback_plan["selection_reason"] = degraded_slot["selection_reason"]
            fallback_plan["degrade_reason"] = degrade_reason
            fallback_plan["reasoning"] = degraded_slot["reasoning"]
            return fallback_plan

        active_input_bindings = input_bindings[:input_count]
        active_output_bindings = output_bindings[:output_count]
        active_input_count = len(active_input_bindings)
        active_output_count = len(active_output_bindings)

        subsystem_plan = empty_subsystem_plan(subsystem_id=subsystem_id, page_id=page_id)
        subsystem_plan.update(
            {
                "implementation_mode": "reuse_template",
                "selection_reason": str(slot.get("selection_reason", "")).strip()
                or f"Selected reusable template {template_id}.",
                "degrade_reason": "",
                "template_binding": {
                    "template_id": template_id,
                    "reasoning": "Matched architecture preferred_template_ids against retrieval bundle.",
                    "selection_reason": str(slot.get("selection_reason", "")).strip()
                    or f"Selected reusable template {template_id}.",
                    "score_breakdown": list(slot.get("score_breakdown", []) or []),
                },
                "node_instances": [
                    {
                        "logic_id": main_logic_id,
                        "module_type": template_id,
                        "page_id": page_id,
                        "template_id": template_id,
                        "parameters": {"name": str(template_doc.get("template_name") or descriptor.get("goal") or subsystem_id)},
                        "input_count": active_input_count,
                        "output_count": active_output_count,
                        "position": {"x": 0, "y": 0},
                        "reasoning": f"Reuse template {template_id} for subsystem {subsystem_id}.",
                    }
                ],
                "edges": [],
                "template_interface_bindings": interface_bindings,
                "imported_signals": self._build_signal_bindings(active_input_bindings, main_logic_id, page_id, "import"),
                "exported_signals": self._build_signal_bindings(active_output_bindings, main_logic_id, page_id, "export"),
                "constraints": [
                    {
                        "constraint_id": f"{subsystem_id}::implementation",
                        "value": "reuse_template",
                        "source": "architecture_plan.subsystem_slots",
                    }
                ],
                "unresolved_items": [],
                "reasoning": str(slot.get("reasoning", "")).strip() or "Template reuse path selected.",
            }
        )
        return subsystem_plan

    def _plan_atomic_fallback(
        self,
        descriptor: Dict[str, Any],
        slot: Dict[str, Any],
        atomic_modules: List[Dict[str, Any]],
        shared_signal_registry: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        subsystem_id = str(descriptor.get("subsystem_id", "")).strip()
        page_id = str(descriptor.get("page_id", "")).strip()
        subsystem_plan = empty_subsystem_plan(subsystem_id=subsystem_id, page_id=page_id)
        primary_doc = self._select_atomic_primary_doc(descriptor, atomic_modules)
        if not primary_doc:
            subsystem_plan.update(
                {
                    "implementation_mode": "atomic_assembly",
                    "selection_reason": str(slot.get("selection_reason", "")).strip()
                    or "No reusable template selected; entering atomic fallback.",
                    "degrade_reason": "No atomic module candidates available for fallback.",
                    "template_interface_bindings": self._descriptor_interface_bindings(descriptor, shared_signal_registry),
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

        interface_bindings = self._descriptor_interface_bindings(descriptor, shared_signal_registry)
        input_bindings = self._bindings_for_direction(interface_bindings, "input")
        output_bindings = self._bindings_for_direction(interface_bindings, "output")
        desired_inputs = len(input_bindings) or 1
        primary_logic_id = f"{subsystem_id}_main"
        primary_parameters = self._default_parameters(primary_doc, str(descriptor.get("goal") or subsystem_id), desired_inputs)
        primary_input_count, primary_output_count = self._resolve_counts(primary_doc, primary_parameters)
        active_input_bindings = self._ensure_binding_count(input_bindings, "input", f"{subsystem_id}_input", primary_input_count)
        active_output_bindings = self._ensure_binding_count(
            output_bindings,
            "output",
            f"{subsystem_id}_output",
            max(1, primary_output_count),
        )
        import_names = [binding["signal_name"] for binding in active_input_bindings]
        export_names = [binding["signal_name"] for binding in active_output_bindings]

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
                "selection_reason": str(slot.get("selection_reason", "")).strip()
                or "No reusable template selected; entering atomic fallback.",
                "degrade_reason": str(slot.get("degrade_reason", "")).strip()
                or "No qualified reusable template was available; used atomic modules.",
                "template_binding": {
                    "template_id": "",
                    "reasoning": "Preferred templates unavailable; fell back to atomic modules.",
                    "degraded": True,
                    "degrade_reason": str(slot.get("degrade_reason", "")).strip()
                    or "No qualified reusable template was available; used atomic modules.",
                    "score_breakdown": list(slot.get("score_breakdown", []) or []),
                },
                "node_instances": node_instances,
                "edges": edges,
                "template_interface_bindings": interface_bindings,
                "imported_signals": self._build_signal_bindings(active_input_bindings, primary_logic_id, page_id, "import"),
                "exported_signals": self._build_signal_bindings(active_output_bindings, primary_logic_id, page_id, "export"),
                "constraints": [
                    {
                        "constraint_id": f"{subsystem_id}::implementation",
                        "value": "atomic_assembly",
                        "source": "architecture_plan.subsystem_slots.fallback_mode",
                    }
                ],
                "unresolved_items": unresolved_items,
                "reasoning": (
                    str(slot.get("reasoning", "")).strip()
                    or "Atomic fallback path selected because no qualified reusable template was available."
                ),
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
        doc_map = build_compilable_doc_map(retrieval_bundle)
        atomic_modules = get_atomic_modules(retrieval_bundle)
        shared_signal_registry = self._shared_signal_registry(
            requirement_spec,
            decomposition_result,
            architecture_plan,
        )
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
                subsystem_plan = self._plan_template_reuse(
                    descriptor,
                    slot,
                    template_doc,
                    atomic_modules,
                    shared_signal_registry,
                )
            else:
                subsystem_plan = self._plan_atomic_fallback(descriptor, slot, atomic_modules, shared_signal_registry)
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
