"""
Coding agent for phase 1 workflow refactor.

This stage is now a deterministic compiler: it consumes assembled Graph IR and
retrieval-backed templates to produce platform JSON plus a structured compile
report.
"""
from __future__ import annotations

import copy
import json
from typing import Any, Dict, List, Set

import config
from utils.graph_ir import CompileReport, CompiledArtifact
from utils.retrieval_bundle_utils import build_compilable_doc_map
from .coding_utils import (
    fill_template,
    generate_short_uuid,
    resolve_input_count,
    resolve_output_count,
)


class CodingAgent:
    """Deterministic compiler from assembled_graph_ir to platform JSON."""

    def __init__(self):
        if config.DEBUG:
            print("[CodingAgent] initialized")

    @staticmethod
    def _normalize_template(template_raw: Any) -> Dict[str, Any]:
        if isinstance(template_raw, list):
            if template_raw and isinstance(template_raw[0], dict):
                return copy.deepcopy(template_raw[0])
            return {}
        if isinstance(template_raw, dict):
            return copy.deepcopy(template_raw)
        return {}

    @staticmethod
    def _assign_stable_id(seed: str, used_ids: Set[str]) -> str:
        return generate_short_uuid(seed, used_ids)

    def _build_stable_id_map(
        self,
        pages: List[Dict[str, Any]],
        subflow_definitions: List[Dict[str, Any]],
        node_instances: List[Dict[str, Any]],
    ) -> Dict[str, str]:
        id_map: Dict[str, str] = {}
        used_ids: Set[str] = set()

        for page in pages:
            page_id = page["page_id"]
            id_map[page_id] = self._assign_stable_id(f"page::{page_id}", used_ids)

        for definition in subflow_definitions:
            definition_id = definition["definition_id"]
            real_id = self._assign_stable_id(f"subflow::{definition_id}", used_ids)
            id_map[definition_id] = real_id
            template_id = definition.get("template_id")
            if template_id:
                id_map[template_id] = real_id

        for node in node_instances:
            instance_id = node["instance_id"]
            id_map[instance_id] = self._assign_stable_id(f"node::{instance_id}", used_ids)

        return id_map

    @staticmethod
    def _build_doc_map(bundle_or_context: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        return build_compilable_doc_map(bundle_or_context)

    @staticmethod
    def _build_reverse_edge_map(
        edges: List[Dict[str, Any]],
        id_map: Dict[str, str],
        warnings: List[str],
    ) -> Dict[str, Dict[int, Dict[str, Any]]]:
        reverse_map: Dict[str, Dict[int, Dict[str, Any]]] = {}
        for edge in edges:
            edge_id = edge.get("edge_id", "edge::unknown")
            source_instance = edge.get("from_instance", "")
            target_instance = edge.get("to_instance", "")
            target_port = int(edge.get("to_port", 0) or 0)

            if source_instance not in id_map:
                warnings.append(f"{edge_id} 引用了不存在的源实例 {source_instance}，该连线已跳过。")
                continue
            if target_instance not in id_map:
                warnings.append(f"{edge_id} 引用了不存在的目标实例 {target_instance}，该连线已跳过。")
                continue

            reverse_map.setdefault(target_instance, {})
            reverse_map[target_instance][target_port] = {
                "id": id_map[source_instance],
                "port": int(edge.get("from_port", 0) or 0),
            }
        return reverse_map

    @staticmethod
    def _build_wires(input_count: int, incoming_map: Dict[int, Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        wires = []
        for index in range(max(0, input_count)):
            if index in incoming_map:
                wires.append([incoming_map[index]])
            else:
                wires.append([])
        return wires

    def _compile_subflow_definition(
        self,
        subflow_definition: Dict[str, Any],
        real_id: str,
    ) -> Dict[str, Any]:
        raw_definition = copy.deepcopy(subflow_definition.get("raw_definition", {}) or {})
        if raw_definition:
            raw_definition["id"] = real_id
            raw_definition.setdefault("type", "subflow")
            raw_definition.setdefault("name", subflow_definition.get("name", ""))
            raw_definition.setdefault("in", [])
            raw_definition.setdefault("out", [])
            return raw_definition

        in_ports = subflow_definition.get("in_ports", []) or []
        out_ports = subflow_definition.get("out_ports", []) or []
        return {
            "id": real_id,
            "type": "subflow",
            "name": subflow_definition.get("name", ""),
            "info": "",
            "in": [
                {
                    "x": int(port.get("x", 60) or 60),
                    "y": int(port.get("y", 60 + index * 40) or 0),
                    "name": port.get("name", ""),
                    "wires": [],
                }
                for index, port in enumerate(in_ports)
            ],
            "out": [
                {
                    "x": int(port.get("x", 420) or 420),
                    "y": int(port.get("y", 60 + index * 40) or 0),
                    "name": port.get("name", ""),
                    "wires": [],
                }
                for index, port in enumerate(out_ports)
            ],
        }

    def _compile_subflow_instance(
        self,
        node: Dict[str, Any],
        parent_scope_id: str,
        real_id: str,
        definition_real_id: str,
        wires: List[List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        position = node.get("position", {}) or {}
        return {
            "id": real_id,
            "type": f"subflow:{definition_real_id}",
            "z": parent_scope_id,
            "name": node.get("parameters", {}).get("name", ""),
            "x": int(position.get("x", 100) or 100),
            "y": int(position.get("y", 100) or 100),
            "wires": wires,
            "inputs": int(node.get("input_count", 0) or 0),
            "outputs": int(node.get("output_count", 0) or 0),
        }

    def compile_graph(
        self,
        assembled_graph_ir: Dict[str, Any],
        bundle_or_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        doc_map = self._build_doc_map(bundle_or_context)
        pages = assembled_graph_ir.get("pages", []) or []
        subflow_definitions = assembled_graph_ir.get("subflow_definitions", []) or []
        node_instances = assembled_graph_ir.get("node_instances", []) or []
        edges = assembled_graph_ir.get("edges", []) or []
        unresolved_items = assembled_graph_ir.get("unresolved_items", []) or []

        flow_objects: List[Dict[str, Any]] = []
        id_map = self._build_stable_id_map(pages, subflow_definitions, node_instances)
        layout_map: Dict[str, Dict[str, int]] = {}
        warnings: List[str] = []

        for page in pages:
            page_id = page["page_id"]
            real_id = id_map[page_id]
            flow_objects.append({
                "id": real_id,
                "type": "tab",
                "label": page.get("label", "自动生成流程"),
                "disabled": False,
                "info": "",
            })

        for definition in subflow_definitions:
            definition_id = definition["definition_id"]
            real_id = id_map[definition_id]
            flow_objects.append(self._compile_subflow_definition(definition, real_id))

        for node in node_instances:
            instance_id = node["instance_id"]
            layout_map[instance_id] = {
                "x": int((node.get("position", {}) or {}).get("x", 0) or 0),
                "y": int((node.get("position", {}) or {}).get("y", 0) or 0),
            }

        reverse_edges = self._build_reverse_edge_map(edges, id_map, warnings)

        for node in node_instances:
            instance_id = node["instance_id"]
            module_type = node.get("module_type", "")
            template_id = node.get("template_id")
            position = node.get("position", {}) or {}

            if node.get("page_id"):
                parent_scope_id = id_map[node["page_id"]]
            elif node.get("subflow_id"):
                parent_scope_id = id_map[node["subflow_id"]]
            else:
                warnings.append(f"{instance_id} 缺少 page_id/subflow_id，已跳过。")
                continue

            input_count = int(node.get("input_count", 0) or 0)
            incoming_map = reverse_edges.get(instance_id, {})
            wires = self._build_wires(input_count, incoming_map)

            if template_id and template_id in id_map:
                flow_objects.append(self._compile_subflow_instance(
                    node=node,
                    parent_scope_id=parent_scope_id,
                    real_id=id_map[instance_id],
                    definition_real_id=id_map[template_id],
                    wires=wires,
                ))
                continue

            module_doc = doc_map.get(module_type)
            if not module_doc:
                warnings.append(f"{instance_id} 缺少 module_type={module_type} 的模板定义，已跳过。")
                continue

            template = self._normalize_template(module_doc.get("template_json", {}))
            template_type = str(template.get("type", ""))

            if template_type == "subflow":
                definition_lookup_key = template_id or module_type
                definition_real_id = id_map.get(definition_lookup_key) or id_map.get(module_type)
                if not definition_real_id:
                    warnings.append(f"{instance_id} 的子流程定义 {module_type} 尚未生成，已跳过。")
                    continue
                flow_objects.append(self._compile_subflow_instance(
                    node=node,
                    parent_scope_id=parent_scope_id,
                    real_id=id_map[instance_id],
                    definition_real_id=definition_real_id,
                    wires=wires,
                ))
                continue

            template_inputs = template.get("inputs", node.get("input_count", 0))
            template_outputs = template.get("outputs", node.get("output_count", 0))
            planned_params = node.get("parameters", {}) or {}

            node_for_fill = {
                "logic_id": node.get("logic_id", instance_id),
                "module_type": module_type,
                "parameters": planned_params,
                "reasoning": node.get("reasoning", ""),
            }
            filled_node = fill_template(
                template=template,
                node=node_for_fill,
                real_id=id_map[instance_id],
                flow_id=parent_scope_id,
                coords={
                    "x": int(position.get("x", 100) or 100),
                    "y": int(position.get("y", 100) or 100),
                },
                wires=wires,
                module_name=module_doc.get("name", module_type),
            )

            if "outputs" not in filled_node:
                filled_node["outputs"] = resolve_output_count(template_outputs, planned_params, module_doc)
            if "inputs" not in filled_node:
                filled_node["inputs"] = resolve_input_count(template_inputs, planned_params, module_doc)

            flow_objects.append(filled_node)

        warnings.extend(item.get("message", "") for item in unresolved_items if item.get("message"))

        artifact = CompiledArtifact(
            json_text=json.dumps(flow_objects, indent=2, ensure_ascii=False),
            flow_objects=flow_objects,
            id_map=id_map,
            layout_map=layout_map,
            compile_report=CompileReport(
                node_count=sum(
                    1 for obj in flow_objects
                    if obj.get("type") not in {"tab", "subflow"}
                ),
                subflow_count=sum(1 for obj in flow_objects if obj.get("type") == "subflow"),
                page_count=sum(1 for obj in flow_objects if obj.get("type") == "tab"),
                warnings=warnings,
            ),
        )

        if config.DEBUG:
            print("\n[JSONCompiler] completed:")
            print(f"   页面数: {artifact.compile_report.page_count}")
            print(f"   子流程定义数: {artifact.compile_report.subflow_count}")
            print(f"   节点数: {artifact.compile_report.node_count}")
            print(f"   警告数: {len(artifact.compile_report.warnings)}")

        return artifact.model_dump()

    def generate_json(self, assembled_graph_ir: Dict[str, Any], bundle_or_context: Dict[str, Any]) -> str:
        """Backwards-compatible wrapper returning only the JSON text."""
        artifact = self.compile_graph(assembled_graph_ir, bundle_or_context)
        return artifact["json_text"]

    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        assembled_graph_ir = state.get("assembled_graph_ir", {})
        retrieval_bundle = state.get("retrieval_bundle", {}) or {}
        compiled_artifact = self.compile_graph(assembled_graph_ir, retrieval_bundle)

        state["compiled_artifact"] = compiled_artifact
        state["current_step"] = "coding_completed"
        return state
