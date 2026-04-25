"""
Coding agent for phase 1 workflow refactor.

This stage is now a deterministic compiler: it consumes assembled Graph IR and
retrieval-backed templates to produce platform JSON plus a structured compile
report.
"""
from __future__ import annotations

import copy
import json
import re
from typing import Any, Dict, List, Set, Tuple

import config
from utils.graph_ir import CompileReport, CompiledArtifact
from utils.retrieval_bundle_utils import build_bundle_doc_map
from .coding_utils import (
    fill_template,
    generate_short_uuid,
    resolve_input_count,
    resolve_output_count,
)


class CodingAgent:
    """Deterministic compiler from assembled_graph_ir to platform JSON."""

    QUOTE_REF_RE = re.compile(r"\[([^:\]]+):(\d+)\]")

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
            if definition_id in id_map:
                real_id = id_map[definition_id]
            else:
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
    def _build_formal_doc_map(retrieval_bundle: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        return build_bundle_doc_map(retrieval_bundle)

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

    @staticmethod
    def _contains_placeholder(value: Any) -> bool:
        if isinstance(value, str):
            return "{{" in value and "}}" in value
        if isinstance(value, dict):
            return any(CodingAgent._contains_placeholder(item) for item in value.values())
        if isinstance(value, list):
            return any(CodingAgent._contains_placeholder(item) for item in value)
        return False

    @classmethod
    def _rewrite_label_references(
        cls,
        value: str,
        id_rewrite: Dict[str, str],
        errors: List[str],
        context: str,
    ) -> str:
        def replace(match: re.Match[str]) -> str:
            raw_id = match.group(1).strip()
            port = match.group(2)
            if raw_id in id_rewrite:
                return f"[{id_rewrite[raw_id]}:{port}]"
            # 跨页面引用不一定属于 subflow body，本轮保留原引用并交给 flow schema 产出诊断。
            return match.group(0)

        return cls.QUOTE_REF_RE.sub(replace, value)

    @staticmethod
    def _remap_flat_wire_targets(
        wires: Any,
        id_rewrite: Dict[str, str],
        errors: List[str],
        context: str,
    ) -> List[Dict[str, Any]]:
        if not isinstance(wires, list):
            errors.append(f"{context} 的 wires 不是列表。")
            return []

        remapped: List[Dict[str, Any]] = []
        for target_index, target in enumerate(wires):
            if not isinstance(target, dict):
                errors.append(f"{context} 的 wires[{target_index}] 不是字典。")
                continue
            next_target = copy.deepcopy(target)
            raw_id = str(next_target.get("id", "")).strip()
            if raw_id in id_rewrite:
                next_target["id"] = id_rewrite[raw_id]
            elif raw_id:
                errors.append(f"{context} 的 wires 目标 {raw_id} 无法重映射。")
            remapped.append(next_target)
        return remapped

    @classmethod
    def _remap_body_wires(
        cls,
        wires: Any,
        id_rewrite: Dict[str, str],
        errors: List[str],
        context: str,
    ) -> List[List[Dict[str, Any]]]:
        if not isinstance(wires, list):
            errors.append(f"{context} 的 wires 不是列表。")
            return []

        remapped_groups: List[List[Dict[str, Any]]] = []
        for group_index, output_group in enumerate(wires):
            if not isinstance(output_group, list):
                errors.append(f"{context} 的 wires[{group_index}] 不是列表。")
                remapped_groups.append([])
                continue
            remapped_groups.append(
                cls._remap_flat_wire_targets(
                    output_group,
                    id_rewrite,
                    errors,
                    f"{context}.wires[{group_index}]",
                )
            )
        return remapped_groups

    def _compile_subflow_body_objects(
        self,
        subflow_definition: Dict[str, Any],
        definition_real_id: str,
        used_ids: Set[str],
    ) -> Tuple[List[Dict[str, Any]], Dict[str, str], List[str]]:
        body_raw = subflow_definition.get("internal_flow_objects", []) or []
        definition_id = str(subflow_definition.get("definition_id", "")).strip()
        template_id = str(subflow_definition.get("template_id", "")).strip()
        raw_definition = subflow_definition.get("raw_definition", {}) or {}
        raw_definition_id = str(raw_definition.get("id", "")).strip()
        context_prefix = definition_id or template_id or definition_real_id
        errors: List[str] = []

        if not body_raw:
            return [], {}, errors
        if not isinstance(body_raw, list):
            return [], {}, [f"{context_prefix} 的 internal_flow_objects 不是列表。"]

        body_id_map: Dict[str, str] = {}
        for index, body_obj in enumerate(body_raw):
            if not isinstance(body_obj, dict):
                errors.append(f"{context_prefix} 的 body[{index}] 不是字典，已跳过。")
                continue
            raw_id = str(body_obj.get("id", "")).strip()
            if not raw_id:
                raw_id = f"missing_body_id_{index}"
                errors.append(f"{context_prefix} 的 body[{index}] 缺少 id，已使用稳定占位 id。")
            if raw_id not in body_id_map:
                body_id_map[raw_id] = self._assign_stable_id(
                    f"subflow_body::{context_prefix}::{raw_id}",
                    used_ids,
                )

        id_rewrite = dict(body_id_map)
        for alias in (raw_definition_id, definition_id, template_id):
            if alias:
                id_rewrite[alias] = definition_real_id
        for body_obj in body_raw:
            if not isinstance(body_obj, dict):
                continue
            parent_id = str(body_obj.get("z", "")).strip()
            if parent_id and parent_id not in body_id_map:
                id_rewrite[parent_id] = definition_real_id

        body_objects: List[Dict[str, Any]] = []
        for index, body_obj in enumerate(body_raw):
            if not isinstance(body_obj, dict):
                continue
            raw_id = str(body_obj.get("id", "")).strip() or f"missing_body_id_{index}"
            real_id = body_id_map.get(raw_id)
            if not real_id:
                continue

            compiled_obj = copy.deepcopy(body_obj)
            if compiled_obj.get("type") in {"tab", "subflow"}:
                errors.append(f"{context_prefix} 的 body 节点 {raw_id} 不应是 tab/subflow，已跳过。")
                continue
            compiled_obj["id"] = real_id
            compiled_obj["z"] = definition_real_id
            if "wires" in compiled_obj:
                compiled_obj["wires"] = self._remap_body_wires(
                    compiled_obj.get("wires", []),
                    id_rewrite,
                    errors,
                    f"{context_prefix}.body[{raw_id}]",
                )
            if isinstance(compiled_obj.get("labelName"), str):
                compiled_obj["labelName"] = self._rewrite_label_references(
                    compiled_obj["labelName"],
                    id_rewrite,
                    errors,
                    f"{context_prefix}.body[{raw_id}]",
                )
            body_objects.append(compiled_obj)

        return body_objects, body_id_map, errors

    def _compile_subflow_definition(
        self,
        subflow_definition: Dict[str, Any],
        real_id: str,
        body_id_map: Dict[str, str] | None = None,
    ) -> Tuple[Dict[str, Any], List[str]]:
        errors: List[str] = []
        body_id_map = body_id_map or {}
        raw_definition = copy.deepcopy(subflow_definition.get("raw_definition", {}) or {})
        if raw_definition:
            original_definition_id = str(raw_definition.get("id", "")).strip()
            raw_definition["id"] = real_id
            raw_definition.setdefault("type", "subflow")
            raw_definition.setdefault("name", subflow_definition.get("name", ""))
            raw_definition.setdefault("in", [])
            raw_definition.setdefault("out", [])
            id_rewrite = dict(body_id_map)
            for alias in (
                original_definition_id,
                str(subflow_definition.get("definition_id", "")).strip(),
                str(subflow_definition.get("template_id", "")).strip(),
            ):
                if alias:
                    id_rewrite[alias] = real_id
            for field_name in ("in", "out"):
                ports = raw_definition.get(field_name, [])
                if not isinstance(ports, list):
                    errors.append(f"{subflow_definition.get('definition_id', real_id)} 的 {field_name} 不是列表。")
                    raw_definition[field_name] = []
                    continue
                for index, port in enumerate(ports):
                    if not isinstance(port, dict):
                        errors.append(f"{subflow_definition.get('definition_id', real_id)} 的 {field_name}[{index}] 不是字典。")
                        continue
                    port["wires"] = self._remap_flat_wire_targets(
                        port.get("wires", []),
                        id_rewrite,
                        errors,
                        f"{subflow_definition.get('definition_id', real_id)}.{field_name}[{index}]",
                    )
            return raw_definition, errors

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
        }, errors

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

    def _compile_graph_with_doc_map(
        self,
        assembled_graph_ir: Dict[str, Any],
        doc_map: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        pages = assembled_graph_ir.get("pages", []) or []
        subflow_definitions = assembled_graph_ir.get("subflow_definitions", []) or []
        node_instances = assembled_graph_ir.get("node_instances", []) or []
        edges = assembled_graph_ir.get("edges", []) or []
        unresolved_items = assembled_graph_ir.get("unresolved_items", []) or []

        flow_objects: List[Dict[str, Any]] = []
        id_map = self._build_stable_id_map(pages, subflow_definitions, node_instances)
        layout_map: Dict[str, Dict[str, int]] = {}
        warnings: List[str] = []
        used_ids: Set[str] = set(id_map.values())
        body_node_count = 0
        dropped_node_count = 0
        missing_template_count = 0
        body_expansion_errors: List[str] = []

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

        compiled_subflow_real_ids: Set[str] = set()
        for definition in subflow_definitions:
            definition_id = definition["definition_id"]
            real_id = id_map[definition_id]
            if real_id in compiled_subflow_real_ids:
                continue
            compiled_subflow_real_ids.add(real_id)
            body_objects, body_id_map, body_errors = self._compile_subflow_body_objects(
                definition,
                real_id,
                used_ids,
            )
            for raw_id, body_real_id in body_id_map.items():
                flow_objects_key = f"body::{definition_id}::{raw_id}"
                id_map[flow_objects_key] = body_real_id
                template_id = str(definition.get("template_id", "")).strip()
                if template_id:
                    id_map[f"body::{template_id}::{raw_id}"] = body_real_id

            compiled_definition, definition_errors = self._compile_subflow_definition(
                definition,
                real_id,
                body_id_map,
            )
            flow_objects.append(compiled_definition)
            flow_objects.extend(body_objects)
            body_node_count += len(body_objects)
            body_expansion_errors.extend(body_errors)
            body_expansion_errors.extend(definition_errors)

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
                dropped_node_count += 1
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
                missing_template_count += 1
                dropped_node_count += 1
                continue

            template = self._normalize_template(module_doc.get("template_json", {}))
            template_type = str(template.get("type", ""))

            if template_type == "subflow":
                definition_lookup_key = template_id or module_type
                definition_real_id = id_map.get(definition_lookup_key) or id_map.get(module_type)
                if not definition_real_id:
                    warnings.append(f"{instance_id} 的子流程定义 {module_type} 尚未生成，已跳过。")
                    dropped_node_count += 1
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
        unresolved_placeholder_count = sum(1 for obj in flow_objects if self._contains_placeholder(obj))

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
                body_node_count=body_node_count,
                dropped_node_count=dropped_node_count,
                missing_template_count=missing_template_count,
                unresolved_placeholder_count=unresolved_placeholder_count,
                body_expansion_errors=body_expansion_errors,
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

    def compile_graph_from_bundle(
        self,
        assembled_graph_ir: Dict[str, Any],
        retrieval_bundle: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Formal compiler entrypoint used by the main workflow."""
        doc_map = self._build_formal_doc_map(retrieval_bundle)
        return self._compile_graph_with_doc_map(assembled_graph_ir, doc_map)

    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        assembled_graph_ir = state.get("assembled_graph_ir", {})
        retrieval_bundle = state.get("retrieval_bundle", {}) or {}
        compiled_artifact = self.compile_graph_from_bundle(assembled_graph_ir, retrieval_bundle)

        state["compiled_artifact"] = compiled_artifact
        state["current_step"] = "coding_completed"
        return state
