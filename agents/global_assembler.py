"""Phase 3 global assembler."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import config
from utils.graph_ir import AssembledGraphIR, EdgeIR, NodeInstanceIR, PageIR, SignalIR
from utils.phase3_adapters import build_legacy_execution_plan, normalize_signal_name
from .assembly_agent import AssemblyAgent
from .coding_utils import resolve_input_count, resolve_output_count


class GlobalAssembler(AssemblyAgent):
    """Assemble subsystem-local IR into the existing Graph IR contract."""

    def __init__(self):
        super().__init__()
        if config.DEBUG:
            print("[GlobalAssembler] initialized")

    @staticmethod
    def _ordered_subsystem_ids(architecture_plan: Dict[str, Any], subsystem_plan_map: Dict[str, Dict[str, Any]]) -> List[str]:
        ordered: List[str] = []
        for slot in architecture_plan.get("subsystem_slots", []) or []:
            subsystem_id = str(slot.get("subsystem_id", "")).strip()
            if subsystem_id and subsystem_id in subsystem_plan_map and subsystem_id not in ordered:
                ordered.append(subsystem_id)
        for subsystem_id in subsystem_plan_map.keys():
            if subsystem_id not in ordered:
                ordered.append(subsystem_id)
        return ordered

    @staticmethod
    def _resolve_counts(module_doc: Dict[str, Any], node: Dict[str, Any]) -> tuple[int, int]:
        input_count = int(node.get("input_count", 0) or 0)
        output_count = int(node.get("output_count", 0) or 0)
        if input_count or output_count:
            return input_count, output_count

        template_json = node.get("template_json", {}) or module_doc.get("template_json", {})
        template = AssemblyAgent._normalize_template(template_json)
        ports_definition = module_doc.get("ports_definition", {}) if isinstance(module_doc, dict) else {}
        if template.get("type") == "subflow":
            return (
                int(module_doc.get("compile_hints", {}).get("input_count", len((ports_definition or {}).get("inputs", []))) or 0),
                int(module_doc.get("compile_hints", {}).get("output_count", len((ports_definition or {}).get("outputs", []))) or 0),
            )
        return (
            int(resolve_input_count(template.get("inputs", 0), dict(node.get("parameters", {}) or {}), module_doc) or 0),
            int(resolve_output_count(template.get("outputs", 0), dict(node.get("parameters", {}) or {}), module_doc) or 0),
        )

    @staticmethod
    def _make_signal(
        signal_id: str,
        naming_hint: str,
        from_instance: str,
        from_port: int,
        to_instance: str,
        to_port: int,
    ) -> SignalIR:
        return SignalIR(
            signal_id=signal_id,
            naming_hint=naming_hint,
            source={"instance_id": from_instance, "port": from_port},
            targets=[{"instance_id": to_instance, "port": to_port}],
        )

    def _select_placeholder_source_doc(self, doc_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        preferred = ("constInput", "swInput", "variable")
        best_doc: Dict[str, Any] = {}
        best_score = -1
        for module_type, doc in doc_map.items():
            template = self._normalize_template(doc.get("template_json", {}))
            if template.get("type") == "subflow":
                continue
            input_count, output_count = self._resolve_counts(doc, {})
            if input_count != 0 or output_count <= 0:
                continue
            score = 1
            for index, preferred_type in enumerate(preferred):
                if preferred_type.lower() in module_type.lower():
                    score = 100 - index
                    break
            if score > best_score:
                best_score = score
                best_doc = doc
        return best_doc

    @staticmethod
    def _placeholder_parameters(module_doc: Dict[str, Any], signal_name: str) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        params_schema = module_doc.get("parameters_schema", {}) if isinstance(module_doc, dict) else {}
        if not isinstance(params_schema, dict):
            params_schema = {}
        if "name" in params_schema:
            params["name"] = signal_name
        if "fixedValue" in params_schema:
            params["fixedValue"] = 0
        return params

    @staticmethod
    def _external_signal_keys(requirement_spec: Dict[str, Any]) -> set[str]:
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

        return {
            normalized
            for value in candidates
            if (normalized := normalize_signal_name(value))
        }

    def assemble(
        self,
        architecture_plan: Dict[str, Any],
        subsystem_plan_map: Dict[str, Dict[str, Any]],
        bundle_or_context: Dict[str, Any],
        requirement_spec: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        requirement_spec = requirement_spec or {}
        doc_map = self._build_doc_map(bundle_or_context)
        external_signal_keys = self._external_signal_keys(requirement_spec)
        pages = [
            PageIR(
                page_id=str(page.get("page_id", "")).strip(),
                label=str(page.get("label", "")).strip() or "自动生成流程",
                kind=str(page.get("kind", "")).strip() or "control",
                order=int(page.get("order", index) or index),
            )
            for index, page in enumerate(architecture_plan.get("pages", []) or [])
            if str(page.get("page_id", "")).strip()
        ]
        if not pages:
            pages = [PageIR(page_id=self.DEFAULT_PAGE_ID, label=self.DEFAULT_PAGE_LABEL, kind="control", order=0)]

        page_offsets = {page.page_id: page.order * 1600 for page in pages}
        page_ids = {page.page_id for page in pages}
        subsystem_positions: Dict[str, Dict[str, int]] = {}
        node_instances: List[NodeInstanceIR] = []
        edges: List[EdgeIR] = []
        signals: List[SignalIR] = []
        unresolved_items: List[Dict[str, Any]] = []
        subflow_definitions: Dict[str, Any] = {}
        logic_to_instance: Dict[Tuple[str, str], str] = {}
        occupied_inputs: Dict[str, set[int]] = {}
        edge_counter = 0

        ordered_subsystems = self._ordered_subsystem_ids(architecture_plan, subsystem_plan_map)
        for subsystem_index, subsystem_id in enumerate(ordered_subsystems):
            subsystem_plan = subsystem_plan_map.get(subsystem_id, {}) or {}
            page_id = str(subsystem_plan.get("page_id", "")).strip() or self.DEFAULT_PAGE_ID
            if page_id not in page_ids:
                unresolved_items.append(
                    {
                        "type": "missing_page",
                        "severity": "error",
                        "subsystem_id": subsystem_id,
                        "message": f"Subsystem references unknown page_id={page_id}, falling back to {self.DEFAULT_PAGE_ID}.",
                        "suggested_fix": "确保 architecture_plan.pages 中存在该 page_id，或修正 subsystem_plan_map 的 page_id。",
                    }
                )
                page_id = self.DEFAULT_PAGE_ID
            subsystem_positions[subsystem_id] = {"x": page_offsets.get(page_id, 0), "y": subsystem_index * 360}

            for node_index, node in enumerate(subsystem_plan.get("node_instances", []) or [], start=1):
                local_logic_id = str(node.get("logic_id", "")).strip() or f"{subsystem_id}_node_{node_index}"
                instance_id = str(node.get("instance_id", "")).strip() or f"node::{subsystem_id}::{local_logic_id}"
                logic_to_instance[(subsystem_id, local_logic_id)] = instance_id
                module_type = str(node.get("module_type") or node.get("template_id") or "").strip()
                module_doc = doc_map.get(module_type, {})
                subflow_definition = self._build_subflow_definition(module_type, module_doc)
                if subflow_definition:
                    subflow_definitions[subflow_definition.template_id] = subflow_definition

                input_count, output_count = self._resolve_counts(module_doc, node)
                raw_position = node.get("position", {}) if isinstance(node.get("position"), dict) else {}
                position = {
                    "x": int(raw_position.get("x", 0) or 0) + page_offsets.get(page_id, 0),
                    "y": int(raw_position.get("y", node_index * 120) or node_index * 120) + subsystem_positions[subsystem_id]["y"],
                }
                template_id = str(node.get("template_id", "")).strip() or None
                if subflow_definition:
                    template_id = subflow_definition.definition_id
                    input_count = subflow_definition.inputs
                    output_count = subflow_definition.outputs

                node_instances.append(
                    NodeInstanceIR(
                        instance_id=instance_id,
                        logic_id=local_logic_id,
                        module_type=module_type,
                        page_id=page_id,
                        subflow_id=None,
                        template_id=template_id,
                        parameters=dict(node.get("parameters", {}) or {}),
                        position=position,
                        input_count=input_count,
                        output_count=output_count,
                        reasoning=str(node.get("reasoning", "")).strip(),
                    )
                )

            for local_edge in subsystem_plan.get("edges", []) or []:
                from_logic = str(local_edge.get("from_node", "")).strip()
                to_logic = str(local_edge.get("to_node", "")).strip()
                from_instance = logic_to_instance.get((subsystem_id, from_logic))
                to_instance = logic_to_instance.get((subsystem_id, to_logic))
                if not from_instance or not to_instance:
                    unresolved_items.append(
                        {
                            "type": "missing_local_edge_endpoint",
                            "severity": "error",
                            "subsystem_id": subsystem_id,
                            "message": f"Local edge references missing nodes: {from_logic} -> {to_logic}.",
                            "suggested_fix": "修正 subsystem_plan_map 中的局部边定义，确保 from_node/to_node 都能映射到真实节点。",
                        }
                    )
                    continue
                from_port = int(local_edge.get("from_port", 0) or 0)
                to_port = int(local_edge.get("to_port", 0) or 0)
                signal_name = str(local_edge.get("signal_name", "")).strip() or f"{subsystem_id}_{from_logic}_to_{to_logic}"
                edge_counter += 1
                signal_id = f"signal::{subsystem_id}::{from_logic}:{from_port}::{to_logic}:{to_port}"
                edges.append(
                    EdgeIR(
                        edge_id=f"edge::{edge_counter}",
                        from_instance=from_instance,
                        from_port=from_port,
                        to_instance=to_instance,
                        to_port=to_port,
                        signal_id=signal_id,
                    )
                )
                signals.append(self._make_signal(signal_id, signal_name, from_instance, from_port, to_instance, to_port))
                occupied_inputs.setdefault(to_instance, set()).add(to_port)

            unresolved_items.extend(list(subsystem_plan.get("unresolved_items", []) or []))

        exports_by_signal: Dict[str, List[Dict[str, Any]]] = {}
        imports: List[Dict[str, Any]] = []
        for subsystem_id in ordered_subsystems:
            subsystem_plan = subsystem_plan_map.get(subsystem_id, {}) or {}
            for binding in subsystem_plan.get("exported_signals", []) or []:
                signal_key = normalize_signal_name(binding.get("signal_name", ""))
                if not signal_key:
                    continue
                exports_by_signal.setdefault(signal_key, []).append(
                    {
                        "subsystem_id": subsystem_id,
                        "instance_id": logic_to_instance.get((subsystem_id, str(binding.get("node_logic_id", "")).strip()), ""),
                        "port_index": int(binding.get("port_index", 0) or 0),
                        "signal_name": str(binding.get("signal_name", "")).strip() or signal_key,
                    }
                )
            for binding in subsystem_plan.get("imported_signals", []) or []:
                imports.append(
                    {
                        "subsystem_id": subsystem_id,
                        "instance_id": logic_to_instance.get((subsystem_id, str(binding.get("node_logic_id", "")).strip()), ""),
                        "port_index": int(binding.get("port_index", 0) or 0),
                        "signal_name": str(binding.get("signal_name", "")).strip(),
                        "page_id": str(binding.get("page_id", "")).strip() or subsystem_plan.get("page_id", self.DEFAULT_PAGE_ID),
                    }
                )

        placeholder_source_doc = self._select_placeholder_source_doc(doc_map)
        placeholder_counter = 0
        for binding in imports:
            target_instance = binding.get("instance_id", "")
            target_port = int(binding.get("port_index", 0) or 0)
            page_id = str(binding.get("page_id", "")).strip() or self.DEFAULT_PAGE_ID
            signal_name = binding.get("signal_name", "")
            if not target_instance:
                continue
            if target_port in occupied_inputs.setdefault(target_instance, set()):
                continue

            signal_key = normalize_signal_name(signal_name)
            export_candidates = [
                item for item in exports_by_signal.get(signal_key, [])
                if item.get("instance_id") and item.get("subsystem_id") != binding.get("subsystem_id")
            ]
            if len(export_candidates) > 1:
                unresolved_items.append(
                    {
                        "type": "ambiguous_shared_signal",
                        "severity": "error",
                        "signal_name": signal_name,
                        "message": f"Multiple exporters found for shared signal {signal_name}.",
                        "suggested_fix": "在 ArchitecturePlanner/SubsystemPlanner 中收敛共享信号归属，确保一个共享信号只有唯一导出方。",
                    }
                )
            if export_candidates:
                export_candidate = export_candidates[0]
                edge_counter += 1
                signal_id = f"signal::shared::{signal_key or edge_counter}::{target_port}"
                edges.append(
                    EdgeIR(
                        edge_id=f"edge::{edge_counter}",
                        from_instance=export_candidate["instance_id"],
                        from_port=int(export_candidate.get("port_index", 0) or 0),
                        to_instance=target_instance,
                        to_port=target_port,
                        signal_id=signal_id,
                    )
                )
                signals.append(
                    self._make_signal(
                        signal_id,
                        export_candidate.get("signal_name", signal_name) or signal_name,
                        export_candidate["instance_id"],
                        int(export_candidate.get("port_index", 0) or 0),
                        target_instance,
                        target_port,
                    )
                )
                occupied_inputs[target_instance].add(target_port)
                continue

            if not placeholder_source_doc:
                unresolved_items.append(
                    {
                        "type": "missing_placeholder_source",
                        "severity": "error",
                        "signal_name": signal_name,
                        "message": f"No placeholder source module available for shared signal {signal_name}.",
                        "suggested_fix": "补齐可作为占位输入源的零输入原子模块，或让该信号由真实子系统导出。",
                    }
                )
                continue

            is_declared_external = signal_key in external_signal_keys
            placeholder_counter += 1
            module_type = str(placeholder_source_doc.get("module_type", "")).strip()
            placeholder_logic_id = f"placeholder_{placeholder_counter}"
            placeholder_instance_id = f"node::placeholder::{signal_key or placeholder_counter}"
            input_count, output_count = self._resolve_counts(placeholder_source_doc, {})
            position = {
                "x": page_offsets.get(page_id, 0),
                "y": placeholder_counter * 90,
            }
            node_instances.append(
                NodeInstanceIR(
                    instance_id=placeholder_instance_id,
                    logic_id=placeholder_logic_id,
                    module_type=module_type,
                    page_id=page_id,
                    subflow_id=None,
                    template_id=None,
                    parameters=self._placeholder_parameters(placeholder_source_doc, signal_name or placeholder_logic_id),
                    position=position,
                    input_count=input_count,
                    output_count=max(1, output_count),
                    reasoning="Synthetic placeholder source injected by GlobalAssembler.",
                )
            )
            if not is_declared_external:
                unresolved_items.append(
                    {
                        "type": "synthetic_shared_signal_source",
                        "severity": "error",
                        "signal_name": signal_name,
                        "message": f"Shared signal {signal_name} has no real exporter; GlobalAssembler injected a synthetic placeholder source.",
                        "suggested_fix": "让真实子系统通过 exported_signals 导出该信号，或在 requirement_spec 中明确它是外部输入/全局模式。",
                    }
                )
            edge_counter += 1
            signal_id = f"signal::placeholder::{signal_key or placeholder_counter}"
            edges.append(
                EdgeIR(
                    edge_id=f"edge::{edge_counter}",
                    from_instance=placeholder_instance_id,
                    from_port=0,
                    to_instance=target_instance,
                    to_port=target_port,
                    signal_id=signal_id,
                )
            )
            signals.append(
                self._make_signal(
                    signal_id,
                    signal_name or placeholder_logic_id,
                    placeholder_instance_id,
                    0,
                    target_instance,
                    target_port,
                )
            )
            occupied_inputs[target_instance].add(target_port)

        legacy_execution_plan = build_legacy_execution_plan(requirement_spec, architecture_plan, subsystem_plan_map)
        assembled = AssembledGraphIR(
            goal=str(architecture_plan.get("goal", "") or requirement_spec.get("scenario_summary", "")),
            pages=pages,
            subflow_definitions=list(subflow_definitions.values()),
            node_instances=node_instances,
            edges=edges,
            signal_registry=signals,
            layout_hints={
                "naming_strategy": architecture_plan.get("naming_strategy", {}) or {},
                "layout_strategy": architecture_plan.get("layout_strategy", {}) or {},
                "page_positions": page_offsets,
                "subsystem_positions": subsystem_positions,
            },
            unresolved_items=unresolved_items,
            source_execution_plan=legacy_execution_plan,
        )

        if config.DEBUG:
            print("[GlobalAssembler] completed")
            print(f"   pages={len(assembled.pages)} nodes={len(assembled.node_instances)} edges={len(assembled.edges)}")

        return assembled.model_dump()

    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        requirement_spec = state.get("requirement_spec", {}) or {}
        architecture_plan = state.get("architecture_plan", {}) or {}
        subsystem_plan_map = state.get("subsystem_plan_map", {}) or {}
        bundle_or_context = state.get("retrieval_bundle") or state.get("retrieval_context", {})
        legacy_execution_plan = build_legacy_execution_plan(requirement_spec, architecture_plan, subsystem_plan_map)
        state["execution_plan"] = legacy_execution_plan
        state["assembled_graph_ir"] = self.assemble(
            architecture_plan=architecture_plan,
            subsystem_plan_map=subsystem_plan_map,
            bundle_or_context=bundle_or_context,
            requirement_spec=requirement_spec,
        )
        state["current_step"] = "global_assembly_completed"
        return state
