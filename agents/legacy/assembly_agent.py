"""
Assembly agent for phase 1 workflow refactor.

状态:
- 正式主链: 否。Phase 3 main chain uses GlobalAssembler instead.
- 当前用途: 保留为 legacy execution_plan -> Graph IR assembler。
- 迁移说明: 共享装配 helper 已抽到 agents/assembly_shared.py；
  agents/assembly_agent.py 仅保留兼容 wrapper。
"""
from __future__ import annotations

from typing import Any, Dict, List

import config
from agents.assembly_shared import AssemblySharedMixin
from agents.coding_utils import (
    resolve_input_count,
    resolve_output_count,
    topological_layout,
)
from utils.graph_ir import (
    AssembledGraphIR,
    EdgeIR,
    NodeInstanceIR,
    PageIR,
    SignalIR,
    SubflowDefinitionIR,
)


class AssemblyAgent(AssemblySharedMixin):
    """Legacy assembly node kept for Phase 1/2 compat coverage."""

    def assemble(
        self,
        execution_plan: Dict[str, Any],
        bundle_or_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        plan_nodes = execution_plan.get("nodes", []) or []
        plan_connections = execution_plan.get("connections", []) or []
        doc_map = self._build_doc_map(bundle_or_context)
        coords_map = topological_layout(plan_nodes, plan_connections)

        pages = [
            PageIR(
                page_id=self.DEFAULT_PAGE_ID,
                label=self.DEFAULT_PAGE_LABEL,
                kind="control",
                order=0,
            )
        ]
        node_instances: List[NodeInstanceIR] = []
        edges: List[EdgeIR] = []
        signals: List[SignalIR] = []
        unresolved_items: List[Dict[str, Any]] = []
        subflow_definitions: Dict[str, SubflowDefinitionIR] = {}

        for index, node in enumerate(plan_nodes, start=1):
            logic_id = str(node.get("logic_id") or f"node_{index}").strip()
            module_type = str(node.get("module_type") or "").strip()
            module_doc = doc_map.get(module_type)
            planned_params = node.get("parameters", {}) or {}
            template = self._normalize_template(module_doc.get("template_json", {})) if module_doc else {}

            if not module_doc:
                unresolved_items.append({
                    "type": "missing_module_doc",
                    "logic_id": logic_id,
                    "module_type": module_type,
                    "message": "retrieval documents do not contain a template definition for this module_type",
                })

            subflow_definition = self._build_subflow_definition(module_type, module_doc)
            if subflow_definition:
                subflow_definitions[subflow_definition.template_id] = subflow_definition

            input_count = resolve_input_count(
                template.get("inputs", 0),
                planned_params,
                module_doc,
            ) if module_doc else 0
            output_count = resolve_output_count(
                template.get("outputs", 0),
                planned_params,
                module_doc,
            ) if module_doc else 0

            # Node instances should point at the canonical subflow definition ID so
            # the compiler can resolve instances deterministically.
            template_id = subflow_definition.definition_id if subflow_definition else None
            if subflow_definition:
                input_count = subflow_definition.inputs
                output_count = subflow_definition.outputs

            node_instances.append(NodeInstanceIR(
                instance_id=f"node::{logic_id}",
                logic_id=logic_id,
                module_type=module_type,
                page_id=self.DEFAULT_PAGE_ID,
                subflow_id=None,
                template_id=template_id,
                parameters=planned_params,
                position=coords_map.get(logic_id, {"x": 100, "y": index * 80}),
                input_count=input_count,
                output_count=output_count,
                reasoning=str(node.get("reasoning", "")),
            ))

        for index, conn in enumerate(plan_connections, start=1):
            from_logic_id = str(conn.get("from_node", "")).strip()
            to_logic_id = str(conn.get("to_node", "")).strip()
            from_port = int(conn.get("from_port_index", 0) or 0)
            to_port = int(conn.get("to_port_index", 0) or 0)

            signal_id = f"signal::{from_logic_id}:{from_port}::{to_logic_id}:{to_port}"
            edges.append(EdgeIR(
                edge_id=f"edge::{index}",
                from_instance=f"node::{from_logic_id}",
                from_port=from_port,
                to_instance=f"node::{to_logic_id}",
                to_port=to_port,
                signal_id=signal_id,
            ))
            signals.append(SignalIR(
                signal_id=signal_id,
                naming_hint=f"{from_logic_id}_to_{to_logic_id}",
                source={
                    "instance_id": f"node::{from_logic_id}",
                    "port": from_port,
                },
                targets=[{
                    "instance_id": f"node::{to_logic_id}",
                    "port": to_port,
                }],
            ))

        assembled = AssembledGraphIR(
            goal=str(execution_plan.get("goal", "")),
            pages=pages,
            subflow_definitions=list(subflow_definitions.values()),
            node_instances=node_instances,
            edges=edges,
            signal_registry=signals,
            layout_hints={"page_positions": coords_map},
            unresolved_items=unresolved_items,
        )

        if config.DEBUG:
            print("\n[AssemblyAgent] completed:")
            print(f"   页面数: {len(assembled.pages)}")
            print(f"   子流程定义数: {len(assembled.subflow_definitions)}")
            print(f"   节点实例数: {len(assembled.node_instances)}")
            print(f"   边数: {len(assembled.edges)}")
            if unresolved_items:
                print(f"   未解决项: {len(unresolved_items)}")

        return assembled.model_dump()

    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        execution_plan = state.get("execution_plan", {})
        bundle_or_context = state.get("retrieval_bundle") or state.get("retrieval_context", {})
        state["assembled_graph_ir"] = self.assemble(execution_plan, bundle_or_context)
        state["current_step"] = "assembly_completed"
        return state


__all__ = ["AssemblyAgent"]
