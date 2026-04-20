"""Legacy execution_plan projection helpers."""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Tuple


def _normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = unicodedata.normalize("NFKC", value).strip()
    return re.sub(r"\s+", " ", text)


def _ordered_subsystem_ids(architecture_plan: Dict[str, Any], subsystem_plan_map: Dict[str, Dict[str, Any]]) -> List[str]:
    ordered: List[str] = []
    for slot in architecture_plan.get("subsystem_slots", []) or []:
        subsystem_id = _normalize_text(slot.get("subsystem_id", ""))
        if subsystem_id and subsystem_id not in ordered and subsystem_id in subsystem_plan_map:
            ordered.append(subsystem_id)
    for subsystem_id in subsystem_plan_map.keys():
        if subsystem_id not in ordered:
            ordered.append(subsystem_id)
    return ordered


def build_legacy_execution_plan(
    requirement_spec: Dict[str, Any],
    architecture_plan: Dict[str, Any],
    subsystem_plan_map: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Build a compat-only flattened execution_plan projection for legacy consumers."""
    if not isinstance(subsystem_plan_map, dict) or not subsystem_plan_map:
        return {
            "goal": "规划失败: Phase 3 未生成任何子系统计划",
            "nodes": [],
            "connections": [],
        }

    nodes: List[Dict[str, Any]] = []
    connections: List[Dict[str, Any]] = []
    local_to_global: Dict[Tuple[str, str], str] = {}
    used_logic_ids = set()

    for subsystem_id in _ordered_subsystem_ids(architecture_plan, subsystem_plan_map):
        subsystem_plan = subsystem_plan_map.get(subsystem_id, {}) or {}
        for node in subsystem_plan.get("node_instances", []) or []:
            local_logic_id = _normalize_text(node.get("logic_id", "")) or f"{subsystem_id}_node_{len(nodes) + 1}"
            global_logic_id = local_logic_id
            if global_logic_id in used_logic_ids:
                global_logic_id = f"{subsystem_id}__{local_logic_id}"
            used_logic_ids.add(global_logic_id)
            local_to_global[(subsystem_id, local_logic_id)] = global_logic_id
            nodes.append(
                {
                    "logic_id": global_logic_id,
                    "module_type": _normalize_text(node.get("module_type", "")),
                    "parameters": dict(node.get("parameters", {}) or {}),
                    "reasoning": _normalize_text(node.get("reasoning", "")),
                }
            )

        for edge in subsystem_plan.get("edges", []) or []:
            from_node = local_to_global.get((subsystem_id, _normalize_text(edge.get("from_node", ""))))
            to_node = local_to_global.get((subsystem_id, _normalize_text(edge.get("to_node", ""))))
            if not from_node or not to_node:
                continue
            connections.append(
                {
                    "from_node": from_node,
                    "from_port_index": int(edge.get("from_port", 0) or 0),
                    "to_node": to_node,
                    "to_port_index": int(edge.get("to_port", 0) or 0),
                }
            )

    scenario_summary = _normalize_text(requirement_spec.get("scenario_summary", ""))
    goal = _normalize_text(architecture_plan.get("goal", "")) or scenario_summary or "Phase 3 兼容执行计划"
    if not nodes:
        goal = "规划失败: Phase 3 未生成任何节点"
    return {"goal": goal, "nodes": nodes, "connections": connections}
