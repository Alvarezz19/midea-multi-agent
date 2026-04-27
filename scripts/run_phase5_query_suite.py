from __future__ import annotations

import json
import sys
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import workflow_trace


OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "phase5_query_suite"


class _CallableNode:
    def __init__(self, fn: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
        self._fn = fn

    def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        return self._fn(state)


def _node_factory(fn: Callable[[dict[str, Any]], dict[str, Any]]) -> Callable[[], _CallableNode]:
    return lambda: _CallableNode(fn)


def _analysis_payload(summary: str, *, keywords: list[str] | None = None) -> dict[str, Any]:
    keywords = list(keywords or [])
    return {
        "retrieval_plan": {
            "queries": [summary],
            "category_l1": "",
            "intent": "phase5_query_suite",
            "detected_operations": [],
            "keywords": keywords,
        },
        "scenario_analysis": {
            "summary": summary,
            "business_goal": summary,
            "system_type": "AHU",
            "equipment_object": "AHU",
            "actuator": "AHU",
            "controlled_variable": "",
            "feedback_variable": "",
            "setpoint_variable": "",
            "output_signal": "",
            "control_strategy": "deterministic_suite",
            "control_mode": "auto",
            "input_signals": [],
            "output_signals": [],
            "operating_conditions": [],
            "interlocks_or_limits": [],
            "calculation_logic": [],
            "ambiguities": [],
            "assumptions": [],
            "confidence": 1.0,
        },
        "metadata": {
            "llm_used": False,
            "cached": False,
            "fallback_used": True,
        },
    }


def _requirement_spec(summary: str) -> dict[str, Any]:
    return {
        "schema_version": "3.0",
        "system_type": "AHU",
        "scenario_summary": summary,
        "subsystems": [],
        "signals": {
            "inputs": [],
            "outputs": [],
            "software_points": [],
            "alarm_points": [],
        },
        "required_pages": ["控制"],
        "global_modes": [],
        "ambiguities": [],
        "assumptions": [],
        "acceptance_criteria": [],
        "confidence": 1.0,
        "warnings": [],
    }


def _fixed_retrieval_bundle() -> dict[str, Any]:
    return {
        "atomic_modules": [
            {
                "module_type": "constInput",
                "name": "Constant Input",
                "description": "Fixed deterministic placeholder source.",
                "category": "logic/basic",
                "parameters_schema": {
                    "name": {"type": "string"},
                    "fixedValue": {"type": "number"},
                },
                "ports_definition": {
                    "inputs": [],
                    "outputs": [{"index": 0, "label": "out"}],
                },
                "template_json": {"type": "constInput", "inputs": 0, "outputs": 1},
            },
            {
                "module_type": "add",
                "name": "Add",
                "description": "Fixed deterministic two-input node.",
                "category": "logic/basic",
                "parameters_schema": {
                    "name": {"type": "string"},
                    "inputCount": {"type": "integer"},
                },
                "ports_definition": {
                    "inputs": [{"index": 0, "label": "in0"}, {"index": 1, "label": "in1"}],
                    "outputs": [{"index": 0, "label": "out"}],
                },
                "template_json": {"type": "add", "inputs": 2, "outputs": 1},
            },
        ],
        "subflow_templates": [],
        "system_patterns": [],
        "style_guides": [],
        "metadata": {
            "selected_case_pattern_id": "phase5_deterministic_suite",
            "retrieved_atomic_count": 2,
            "retrieved_subflow_count": 0,
            "retrieved_pattern_count": 0,
        },
    }


def _retrieval_context_from_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    return {
        "query": "phase5 deterministic suite",
        "relevant_nodes": list(bundle.get("atomic_modules", []) or []),
        "similar_cases": [],
        "metadata": {
            "retrieved_count": len(bundle.get("atomic_modules", []) or []),
            "avg_confidence_score": 1.0,
            "intent": "phase5_query_suite",
            "detected_operations": [],
            "query_variants_used": 1,
        },
    }


def _set_analysis_state(
    state: dict[str, Any],
    summary: str,
    *,
    retry_counts_by_scope: dict[str, int] | None = None,
) -> dict[str, Any]:
    state["analysis_result"] = _analysis_payload(summary, keywords=["AHU", "Phase5", "deterministic"])
    state["requirement_spec"] = _requirement_spec(summary)
    if retry_counts_by_scope is not None:
        state["retry_counts_by_scope"] = {
            "planning": int(retry_counts_by_scope.get("planning", 0)),
            "assembly": int(retry_counts_by_scope.get("assembly", 0)),
            "compile": int(retry_counts_by_scope.get("compile", 0)),
        }
        state["retry_count"] = sum(state["retry_counts_by_scope"].values())
    state["current_step"] = "analysis_completed"
    return state


def _set_retrieval_state(state: dict[str, Any]) -> dict[str, Any]:
    bundle = _fixed_retrieval_bundle()
    state["retrieval_bundle"] = bundle
    state["retrieval_context"] = _retrieval_context_from_bundle(bundle)
    state["current_step"] = "retrieval_completed"
    return state


def _base_architecture_payload(goal: str) -> tuple[dict[str, Any], dict[str, Any]]:
    decomposition_result = {
        "pages": [{"page_id": "page_control", "label": "控制", "kind": "control", "order": 0}],
        "subsystem_descriptors": [],
        "shared_signal_registry": [],
        "template_needs": [],
        "planning_order": [],
        "warnings": [],
    }
    architecture_plan = {
        "goal": goal,
        "pages": [{"page_id": "page_control", "label": "控制", "kind": "control", "order": 0}],
        "subsystem_slots": [],
        "shared_signal_registry": [],
        "global_constraints": [],
        "naming_strategy": {},
        "layout_strategy": {},
        "pattern_bindings": [],
        "warnings": [],
    }
    return decomposition_result, architecture_plan


def _set_verification_report(state: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    state["verification_report"] = report
    state["final_output"] = {
        "json_text": (state.get("compiled_artifact", {}) or {}).get("json_text", ""),
        "compile_report": (state.get("compiled_artifact", {}) or {}).get("compile_report", {}),
        "verification_report": report,
    }
    state["current_step"] = "verification_completed"
    return state


def _simple_compiled_artifact(node_count: int = 1) -> dict[str, Any]:
    return {
        "json_text": "[]",
        "flow_objects": [],
        "id_map": {},
        "layout_map": {},
        "compile_report": {
            "page_count": 1,
            "subflow_count": 0,
            "node_count": node_count,
            "warnings": [],
        },
    }


def _shared_signal_owner(state: dict[str, Any], canonical_signal_key: str = "supply_fan_available") -> str:
    registry = ((state.get("architecture_plan", {}) or {}).get("shared_signal_registry", []) or [])
    for entry in registry:
        signal_key = str(
            entry.get("canonical_signal_key")
            or entry.get("signal_key")
            or entry.get("signal_name")
            or ""
        ).strip()
        if signal_key == canonical_signal_key:
            return str(entry.get("owner_subsystem_id", "")).strip()
    return ""


@dataclass(frozen=True)
class Phase5Case:
    case_id: str
    name: str
    query: str
    expected_verification_status: str
    expected_route_decision: str
    expected_repair_scope: str
    build_node_factories: Callable[[], dict[str, Callable[[], _CallableNode]]]
    expected_reject_reason: str = ""
    expected_repair_reject_category: str = ""
    expected_min_repair_rounds: int = 0
    expected_unresolved_types: tuple[str, ...] = ()


def _success_analysis(state: dict[str, Any]) -> dict[str, Any]:
    return _set_analysis_state(state, "Phase 5 deterministic success")


def _success_retrieval(state: dict[str, Any]) -> dict[str, Any]:
    return _set_retrieval_state(state)


def _success_architecture(state: dict[str, Any]) -> dict[str, Any]:
    decomposition_result, architecture_plan = _base_architecture_payload("phase5 success")
    decomposition_result["subsystem_descriptors"] = [
        {"subsystem_id": "supply_fan_ctrl", "imports": [], "exports": ["supply_fan_enable"]},
    ]
    decomposition_result["planning_order"] = ["supply_fan_ctrl"]
    architecture_plan["subsystem_slots"] = [
        {
            "subsystem_id": "supply_fan_ctrl",
            "page_id": "page_control",
            "selection_reason": "deterministic success",
            "degrade_reason": "",
        },
    ]
    state["decomposition_result"] = decomposition_result
    state["architecture_plan"] = architecture_plan
    state["current_step"] = "architecture_planned"
    return state


def _success_subsystem(state: dict[str, Any]) -> dict[str, Any]:
    state["subsystem_plan_map"] = {
        "supply_fan_ctrl": {
            "subsystem_id": "supply_fan_ctrl",
            "page_id": "page_control",
            "implementation_mode": "atomic_assembly",
            "template_binding": {},
            "selection_reason": "deterministic success",
            "degrade_reason": "",
            "node_instances": [{"logic_id": "fan_main"}],
            "edges": [],
            "imported_signals": [],
            "exported_signals": [],
            "constraints": [],
            "unresolved_items": [],
            "reasoning": "success",
        }
    }
    state["current_step"] = "subsystem_planned"
    return state


def _success_global_assembly(state: dict[str, Any]) -> dict[str, Any]:
    state["execution_plan"] = {"goal": "phase5 success", "nodes": [{"logic_id": "fan_main"}], "connections": []}
    state["assembled_graph_ir"] = {
        "graph_ir_version": "2.0",
        "goal": "phase5 success",
        "pages": [{"page_id": "page_control", "label": "控制", "kind": "control", "order": 0}],
        "subflow_definitions": [],
        "node_instances": [{"instance_id": "node::fan_main", "logic_id": "fan_main", "input_count": 0, "output_count": 1}],
        "edges": [],
        "signal_registry": [],
        "layout_hints": {},
        "unresolved_items": [],
        "source_execution_plan": state["execution_plan"],
    }
    state["current_step"] = "global_assembly_completed"
    return state


def _success_coding(state: dict[str, Any]) -> dict[str, Any]:
    state["compiled_artifact"] = _simple_compiled_artifact(node_count=1)
    state["generated_code"] = state["compiled_artifact"]["json_text"]
    state["current_step"] = "coding_completed"
    return state


def _success_verifier(state: dict[str, Any]) -> dict[str, Any]:
    return _set_verification_report(
        state,
        {
            "status": "passed",
            "repair_scope": "none",
            "issue_summary": "结构校验通过。",
            "issues": [],
            "warnings": [],
            "metrics": {},
        },
    )


def _planning_repair_analysis(state: dict[str, Any]) -> dict[str, Any]:
    return _set_analysis_state(state, "Phase 5 planning repair success")


def _planning_repair_retrieval(state: dict[str, Any]) -> dict[str, Any]:
    return _set_retrieval_state(state)


def _planning_repair_architecture(state: dict[str, Any]) -> dict[str, Any]:
    decomposition_result, architecture_plan = _base_architecture_payload("phase5 planning repair")
    shared_signal_entry = {
        "signal_name": "supply_fan_available_flag",
        "signal_key": "supply_fan_available",
        "canonical_signal_key": "supply_fan_available",
        "owner_subsystem_id": "",
        "allowed_external": False,
        "required_exporter_count": 1,
        "consumers": ["heater_ctrl"],
        "candidate_exporters": ["supply_fan_ctrl"],
        "resolution_status": "missing_exporter",
        "resolution_evidence": ["consumers=heater_ctrl", "exporters=supply_fan_ctrl"],
        "source_reason": "planner projected consumer without owner",
    }
    decomposition_result["subsystem_descriptors"] = [
        {
            "subsystem_id": "supply_fan_ctrl",
            "imports": [],
            "exports": ["supply_fan_available_flag"],
            "interface_bindings": [
                {
                    "signal_name": "supply_fan_available_flag",
                    "signal_key": "supply_fan_available_flag",
                    "canonical_signal_key": "supply_fan_available",
                    "direction": "output",
                    "binding_kind": "shared_signal",
                    "allowed_external": False,
                    "owner_subsystem_id": "",
                    "port_index": 0,
                }
            ],
        },
        {
            "subsystem_id": "heater_ctrl",
            "imports": ["supply_fan_available_flag"],
            "exports": ["heater_enable"],
            "interface_bindings": [
                {
                    "signal_name": "supply_fan_available_flag",
                    "signal_key": "supply_fan_available_flag",
                    "canonical_signal_key": "supply_fan_available",
                    "direction": "input",
                    "binding_kind": "shared_signal",
                    "allowed_external": False,
                    "owner_subsystem_id": "",
                    "port_index": 0,
                }
            ],
        },
    ]
    decomposition_result["shared_signal_registry"] = [dict(shared_signal_entry)]
    decomposition_result["planning_order"] = ["supply_fan_ctrl", "heater_ctrl"]
    architecture_plan["subsystem_slots"] = [
        {"subsystem_id": "supply_fan_ctrl", "page_id": "page_control", "selection_reason": "fan slot", "degrade_reason": ""},
        {"subsystem_id": "heater_ctrl", "page_id": "page_control", "selection_reason": "heater slot", "degrade_reason": ""},
    ]
    architecture_plan["shared_signal_registry"] = [dict(shared_signal_entry)]
    state["decomposition_result"] = decomposition_result
    state["architecture_plan"] = architecture_plan
    state["current_step"] = "architecture_planned"
    return state


def _planning_repair_subsystem(state: dict[str, Any]) -> dict[str, Any]:
    owner = _shared_signal_owner(state)
    exported_signals = []
    if owner == "supply_fan_ctrl":
        exported_signals = [
            {
                "signal_name": "supply_fan_available_flag",
                "signal_key": "supply_fan_available_flag",
                "canonical_signal_key": "supply_fan_available",
                "binding_kind": "shared_signal",
                "allowed_external": False,
            }
        ]
    state["subsystem_plan_map"] = {
        "supply_fan_ctrl": {
            "subsystem_id": "supply_fan_ctrl",
            "page_id": "page_control",
            "implementation_mode": "reuse_template",
            "template_binding": {"template_id": "fan_template"},
            "selection_reason": "repair planning case",
            "degrade_reason": "",
            "node_instances": [{"logic_id": "fan_main"}],
            "edges": [],
            "imported_signals": [],
            "exported_signals": exported_signals,
            "constraints": [],
            "unresolved_items": [],
            "reasoning": "fan planner",
        },
        "heater_ctrl": {
            "subsystem_id": "heater_ctrl",
            "page_id": "page_control",
            "implementation_mode": "reuse_template",
            "template_binding": {"template_id": "heater_template"},
            "selection_reason": "repair planning case",
            "degrade_reason": "",
            "node_instances": [{"logic_id": "heater_main"}],
            "edges": [],
            "imported_signals": [
                {
                    "signal_name": "supply_fan_available_flag",
                    "signal_key": "supply_fan_available_flag",
                    "canonical_signal_key": "supply_fan_available",
                    "binding_kind": "shared_signal",
                    "allowed_external": False,
                }
            ],
            "exported_signals": [],
            "constraints": [],
            "unresolved_items": [],
            "reasoning": "heater planner",
        },
    }
    state["current_step"] = "subsystem_planned"
    return state


def _planning_repair_global_assembly(state: dict[str, Any]) -> dict[str, Any]:
    owner = _shared_signal_owner(state)
    unresolved_items = []
    if owner != "supply_fan_ctrl":
        unresolved_items.append(
            {
                "type": "synthetic_shared_signal_source",
                "severity": "error",
                "scope": "planning",
                "signal_name": "supply_fan_available_flag",
                "signal_key": "supply_fan_available_flag",
                "canonical_signal_key": "supply_fan_available",
                "binding_kind": "shared_signal",
                "allowed_external": False,
                "owner_subsystem_id": "",
                "candidate_exporters": ["supply_fan_ctrl"],
                "consumer_subsystem_ids": ["heater_ctrl"],
                "resolution_status": "missing_exporter",
                "resolution_hint": "当前没有可用的真实导出方，只能注入占位源。",
                "message": "Shared signal supply_fan_available_flag has no real exporter.",
                "suggested_fix": "Rebind the shared signal owner.",
            }
        )
    state["execution_plan"] = {"goal": "phase5 planning repair", "nodes": [], "connections": []}
    state["assembled_graph_ir"] = {
        "graph_ir_version": "2.0",
        "goal": "phase5 planning repair",
        "pages": [{"page_id": "page_control", "label": "控制", "kind": "control", "order": 0}],
        "subflow_definitions": [],
        "node_instances": [],
        "edges": [],
        "signal_registry": [],
        "layout_hints": {},
        "unresolved_items": unresolved_items,
        "source_execution_plan": state["execution_plan"],
    }
    state["current_step"] = "global_assembly_completed"
    return state


def _planning_repair_coding(state: dict[str, Any]) -> dict[str, Any]:
    state["compiled_artifact"] = _simple_compiled_artifact(node_count=2)
    state["generated_code"] = state["compiled_artifact"]["json_text"]
    state["current_step"] = "coding_completed"
    return state


def _planning_repair_verifier(state: dict[str, Any]) -> dict[str, Any]:
    unresolved_items = (state.get("assembled_graph_ir", {}) or {}).get("unresolved_items", []) or []
    if unresolved_items:
        report = {
            "status": "retryable_error",
            "repair_scope": "planning",
            "issue_summary": "发现 1 个结构错误。",
            "issues": [
                {
                    "issue_id": "IR-PL-001",
                    "scope": "planning",
                    "target_id": "supply_fan_available_flag",
                    "rule_id": "ir.unresolved.synthetic_shared_signal_source",
                    "message": unresolved_items[0]["message"],
                    "repair_payload": {
                        "signal_name": "supply_fan_available_flag",
                        "canonical_signal_key": "supply_fan_available",
                        "binding_kind": "shared_signal",
                        "allowed_external": False,
                        "candidate_exporters": ["supply_fan_ctrl"],
                        "consumer_subsystem_ids": ["heater_ctrl"],
                        "owner_subsystem_id": "",
                        "resolution_status": "missing_exporter",
                    },
                }
            ],
            "warnings": [],
            "metrics": {},
        }
    else:
        report = {
            "status": "passed",
            "repair_scope": "none",
            "issue_summary": "修复后通过。",
            "issues": [],
            "warnings": [],
            "metrics": {},
        }
    return _set_verification_report(state, report)


def _ambiguous_reject_analysis(state: dict[str, Any]) -> dict[str, Any]:
    return _set_analysis_state(state, "Phase 5 ambiguous reject")


def _ambiguous_reject_retrieval(state: dict[str, Any]) -> dict[str, Any]:
    return _set_retrieval_state(state)


def _ambiguous_reject_architecture(state: dict[str, Any]) -> dict[str, Any]:
    decomposition_result, architecture_plan = _base_architecture_payload("phase5 ambiguous reject")
    shared_signal_entry = {
        "signal_name": "supply_fan_available_flag",
        "signal_key": "supply_fan_available",
        "canonical_signal_key": "supply_fan_available",
        "owner_subsystem_id": "",
        "allowed_external": False,
        "required_exporter_count": 1,
        "consumers": ["heater_ctrl"],
        "candidate_exporters": ["backup_ctrl", "supply_fan_ctrl"],
        "resolution_status": "ambiguous",
        "resolution_evidence": [
            "consumers=heater_ctrl",
            "exporters=backup_ctrl, supply_fan_ctrl",
            "multiple exporter candidates detected",
        ],
        "source_reason": "planner projected ambiguous owner",
    }
    decomposition_result["subsystem_descriptors"] = [
        {
            "subsystem_id": "supply_fan_ctrl",
            "imports": [],
            "exports": ["supply_fan_available_flag"],
            "interface_bindings": [
                {
                    "signal_name": "supply_fan_available_flag",
                    "signal_key": "supply_fan_available_flag",
                    "canonical_signal_key": "supply_fan_available",
                    "direction": "output",
                    "binding_kind": "shared_signal",
                    "allowed_external": False,
                    "owner_subsystem_id": "",
                    "port_index": 0,
                }
            ],
        },
        {
            "subsystem_id": "backup_ctrl",
            "imports": [],
            "exports": ["supply_fan_available_flag"],
            "interface_bindings": [
                {
                    "signal_name": "supply_fan_available_flag",
                    "signal_key": "supply_fan_available_flag",
                    "canonical_signal_key": "supply_fan_available",
                    "direction": "output",
                    "binding_kind": "shared_signal",
                    "allowed_external": False,
                    "owner_subsystem_id": "",
                    "port_index": 0,
                }
            ],
        },
        {
            "subsystem_id": "heater_ctrl",
            "imports": ["supply_fan_available_flag"],
            "exports": [],
            "interface_bindings": [
                {
                    "signal_name": "supply_fan_available_flag",
                    "signal_key": "supply_fan_available_flag",
                    "canonical_signal_key": "supply_fan_available",
                    "direction": "input",
                    "binding_kind": "shared_signal",
                    "allowed_external": False,
                    "owner_subsystem_id": "",
                    "port_index": 0,
                }
            ],
        },
    ]
    decomposition_result["shared_signal_registry"] = [dict(shared_signal_entry)]
    decomposition_result["planning_order"] = ["supply_fan_ctrl", "backup_ctrl", "heater_ctrl"]
    architecture_plan["subsystem_slots"] = [
        {"subsystem_id": "supply_fan_ctrl", "page_id": "page_control", "selection_reason": "fan slot", "degrade_reason": ""},
        {"subsystem_id": "backup_ctrl", "page_id": "page_control", "selection_reason": "backup slot", "degrade_reason": ""},
        {"subsystem_id": "heater_ctrl", "page_id": "page_control", "selection_reason": "heater slot", "degrade_reason": ""},
    ]
    architecture_plan["shared_signal_registry"] = [dict(shared_signal_entry)]
    state["decomposition_result"] = decomposition_result
    state["architecture_plan"] = architecture_plan
    state["current_step"] = "architecture_planned"
    return state


def _ambiguous_reject_subsystem(state: dict[str, Any]) -> dict[str, Any]:
    shared_export = {
        "signal_name": "supply_fan_available_flag",
        "signal_key": "supply_fan_available_flag",
        "canonical_signal_key": "supply_fan_available",
        "binding_kind": "shared_signal",
        "allowed_external": False,
    }
    state["subsystem_plan_map"] = {
        "supply_fan_ctrl": {
            "subsystem_id": "supply_fan_ctrl",
            "page_id": "page_control",
            "implementation_mode": "reuse_template",
            "template_binding": {"template_id": "fan_template"},
            "selection_reason": "ambiguous reject",
            "degrade_reason": "",
            "node_instances": [{"logic_id": "fan_main"}],
            "edges": [],
            "imported_signals": [],
            "exported_signals": [dict(shared_export)],
            "constraints": [],
            "unresolved_items": [],
            "reasoning": "fan",
        },
        "backup_ctrl": {
            "subsystem_id": "backup_ctrl",
            "page_id": "page_control",
            "implementation_mode": "reuse_template",
            "template_binding": {"template_id": "fan_template"},
            "selection_reason": "ambiguous reject",
            "degrade_reason": "",
            "node_instances": [{"logic_id": "backup_fan_main"}],
            "edges": [],
            "imported_signals": [],
            "exported_signals": [dict(shared_export)],
            "constraints": [],
            "unresolved_items": [],
            "reasoning": "backup",
        },
        "heater_ctrl": {
            "subsystem_id": "heater_ctrl",
            "page_id": "page_control",
            "implementation_mode": "reuse_template",
            "template_binding": {"template_id": "heater_template"},
            "selection_reason": "ambiguous reject",
            "degrade_reason": "",
            "node_instances": [{"logic_id": "heater_main"}],
            "edges": [],
            "imported_signals": [
                {
                    "signal_name": "supply_fan_available_flag",
                    "signal_key": "supply_fan_available_flag",
                    "canonical_signal_key": "supply_fan_available",
                    "binding_kind": "shared_signal",
                    "allowed_external": False,
                }
            ],
            "exported_signals": [],
            "constraints": [],
            "unresolved_items": [],
            "reasoning": "heater",
        },
    }
    state["current_step"] = "subsystem_planned"
    return state


def _ambiguous_reject_global_assembly(state: dict[str, Any]) -> dict[str, Any]:
    state["execution_plan"] = {"goal": "phase5 ambiguous reject", "nodes": [], "connections": []}
    state["assembled_graph_ir"] = {
        "graph_ir_version": "2.0",
        "goal": "phase5 ambiguous reject",
        "pages": [{"page_id": "page_control", "label": "控制", "kind": "control", "order": 0}],
        "subflow_definitions": [],
        "node_instances": [],
        "edges": [],
        "signal_registry": [],
        "layout_hints": {},
        "unresolved_items": [
            {
                "type": "ambiguous_shared_signal",
                "severity": "error",
                "scope": "planning",
                "signal_name": "supply_fan_available_flag",
                "signal_key": "supply_fan_available_flag",
                "canonical_signal_key": "supply_fan_available",
                "binding_kind": "shared_signal",
                "allowed_external": False,
                "owner_subsystem_id": "",
                "candidate_exporters": ["backup_ctrl", "supply_fan_ctrl"],
                "consumer_subsystem_ids": ["heater_ctrl"],
                "resolution_status": "ambiguous",
                "resolution_hint": "共享信号存在多个候选导出方，尚未收敛。",
                "resolution_evidence": [
                    "consumers=heater_ctrl",
                    "exporters=backup_ctrl, supply_fan_ctrl",
                    "multiple exporter candidates detected",
                ],
                "message": "Shared signal supply_fan_available_flag has multiple candidate exporters.",
                "suggested_fix": "Narrow the owner to a single exporter.",
            }
        ],
        "source_execution_plan": state["execution_plan"],
    }
    state["current_step"] = "global_assembly_completed"
    return state


def _ambiguous_reject_coding(state: dict[str, Any]) -> dict[str, Any]:
    state["compiled_artifact"] = _simple_compiled_artifact(node_count=3)
    state["generated_code"] = state["compiled_artifact"]["json_text"]
    state["current_step"] = "coding_completed"
    return state


def _ambiguous_reject_verifier(state: dict[str, Any]) -> dict[str, Any]:
    report = {
        "status": "retryable_error",
        "repair_scope": "planning",
        "issue_summary": "共享信号归属歧义未收敛。",
        "issues": [
            {
                "issue_id": "IR-AMB-001",
                "scope": "planning",
                "target_id": "supply_fan_available_flag",
                "rule_id": "ir.unresolved.ambiguous_shared_signal",
                "message": "Shared signal supply_fan_available_flag has multiple candidate exporters.",
                "repair_payload": {
                    "signal_name": "supply_fan_available_flag",
                    "canonical_signal_key": "supply_fan_available",
                    "binding_kind": "shared_signal",
                    "allowed_external": False,
                    "candidate_exporters": ["backup_ctrl", "supply_fan_ctrl"],
                    "consumer_subsystem_ids": ["heater_ctrl"],
                    "owner_subsystem_id": "",
                    "resolution_status": "ambiguous",
                },
            }
        ],
        "warnings": [],
        "metrics": {},
    }
    return _set_verification_report(state, report)


def _assembly_repair_analysis(state: dict[str, Any]) -> dict[str, Any]:
    return _set_analysis_state(state, "Phase 5 assembly repair success")


def _assembly_repair_retrieval(state: dict[str, Any]) -> dict[str, Any]:
    return _set_retrieval_state(state)


def _assembly_repair_architecture(state: dict[str, Any]) -> dict[str, Any]:
    decomposition_result, architecture_plan = _base_architecture_payload("phase5 assembly repair")
    decomposition_result["planning_order"] = ["heater_ctrl"]
    decomposition_result["subsystem_descriptors"] = [{"subsystem_id": "heater_ctrl", "imports": [], "exports": []}]
    architecture_plan["subsystem_slots"] = [
        {"subsystem_id": "heater_ctrl", "page_id": "page_control", "selection_reason": "assembly slot", "degrade_reason": ""},
    ]
    state["decomposition_result"] = decomposition_result
    state["architecture_plan"] = architecture_plan
    state["current_step"] = "architecture_planned"
    return state


def _assembly_repair_subsystem(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("subsystem_plan_map"):
        state["current_step"] = "subsystem_planned"
        return state
    state["subsystem_plan_map"] = {
        "heater_ctrl": {
            "subsystem_id": "heater_ctrl",
            "page_id": "page_control",
            "implementation_mode": "atomic_assembly",
            "template_binding": {},
            "selection_reason": "assembly repair case",
            "degrade_reason": "",
            "node_instances": [{"logic_id": "heater_source"}, {"logic_id": "heater_main"}],
            "edges": [
                {
                    "edge_id": "edge::valid",
                    "from_node": "heater_source",
                    "from_port": 0,
                    "to_node": "heater_main",
                    "to_port": 0,
                    "signal_name": "heater_enable",
                },
                {
                    "edge_id": "edge::ghost_remove",
                    "from_node": "ghost_source",
                    "from_port": 0,
                    "to_node": "heater_main",
                    "to_port": 0,
                    "signal_name": "schedule_enable",
                },
            ],
            "imported_signals": [],
            "exported_signals": [],
            "constraints": [],
            "unresolved_items": [],
            "reasoning": "assembly repair case",
        }
    }
    state["current_step"] = "subsystem_planned"
    return state


def _assembly_repair_global_assembly(state: dict[str, Any]) -> dict[str, Any]:
    subsystem_plan = (state.get("subsystem_plan_map", {}) or {}).get("heater_ctrl", {}) or {}
    has_invalid_edge = any(
        str(edge.get("edge_id", "")).strip() == "edge::ghost_remove"
        for edge in subsystem_plan.get("edges", []) or []
    )
    unresolved_items = []
    if has_invalid_edge:
        unresolved_items.append(
            {
                "type": "missing_local_edge_endpoint",
                "severity": "error",
                "scope": "assembly",
                "subsystem_id": "heater_ctrl",
                "edge_locator": {
                    "subsystem_id": "heater_ctrl",
                    "edge_id": "edge::ghost_remove",
                    "edge_ids": ["edge::ghost_remove"],
                    "from_node": "ghost_source",
                    "to_node": "heater_main",
                },
                "edge_ids": ["edge::ghost_remove"],
                "from_node": "ghost_source",
                "to_node": "heater_main",
                "reason": "missing_local_edge_endpoint",
                "message": "Local edge references missing nodes.",
                "suggested_fix": "Remove the invalid local edge.",
            }
        )
    unresolved_items.extend(list(subsystem_plan.get("unresolved_items", []) or []))
    state["execution_plan"] = {"goal": "phase5 assembly repair", "nodes": [], "connections": []}
    state["assembled_graph_ir"] = {
        "graph_ir_version": "2.0",
        "goal": "phase5 assembly repair",
        "pages": [{"page_id": "page_control", "label": "控制", "kind": "control", "order": 0}],
        "subflow_definitions": [],
        "node_instances": [{"instance_id": "node::heater_main", "logic_id": "heater_main", "input_count": 1, "output_count": 1}],
        "edges": [],
        "signal_registry": [],
        "layout_hints": {},
        "unresolved_items": unresolved_items,
        "source_execution_plan": state["execution_plan"],
    }
    state["current_step"] = "global_assembly_completed"
    return state


def _assembly_repair_coding(state: dict[str, Any]) -> dict[str, Any]:
    state["compiled_artifact"] = _simple_compiled_artifact(node_count=2)
    state["generated_code"] = state["compiled_artifact"]["json_text"]
    state["current_step"] = "coding_completed"
    return state


def _assembly_repair_verifier(state: dict[str, Any]) -> dict[str, Any]:
    unresolved_items = (state.get("assembled_graph_ir", {}) or {}).get("unresolved_items", []) or []
    issue = next(
        (
            item for item in unresolved_items
            if str(item.get("type", "")).strip() == "missing_local_edge_endpoint"
            and str(item.get("severity", "")).strip().lower() == "error"
        ),
        {},
    )
    if issue:
        report = {
            "status": "retryable_error",
            "repair_scope": "assembly",
            "issue_summary": "存在局部边端点缺失。",
            "issues": [
                {
                    "issue_id": "IR-ASM-001",
                    "scope": "assembly",
                    "target_id": "heater_ctrl",
                    "rule_id": "ir.unresolved.missing_local_edge_endpoint",
                    "message": "Local edge references missing nodes.",
                    "repair_payload": {
                        "subsystem_id": "heater_ctrl",
                        "edge_ids": ["edge::ghost_remove"],
                        "from_node": "ghost_source",
                        "to_node": "heater_main",
                        "reason": "missing_local_edge_endpoint",
                    },
                }
            ],
            "warnings": [],
            "metrics": {},
        }
    else:
        report = {
            "status": "passed",
            "repair_scope": "none",
            "issue_summary": "修复后通过。",
            "issues": [],
            "warnings": [],
            "metrics": {},
        }
    return _set_verification_report(state, report)


def _compile_repair_analysis(state: dict[str, Any]) -> dict[str, Any]:
    return _set_analysis_state(state, "Phase 5 compile repair success")


def _compile_repair_retrieval(state: dict[str, Any]) -> dict[str, Any]:
    return _set_retrieval_state(state)


def _compile_repair_architecture(state: dict[str, Any]) -> dict[str, Any]:
    decomposition_result, architecture_plan = _base_architecture_payload("phase5 compile repair")
    decomposition_result["planning_order"] = ["compile_case"]
    decomposition_result["subsystem_descriptors"] = [{"subsystem_id": "compile_case", "imports": [], "exports": []}]
    architecture_plan["subsystem_slots"] = [
        {"subsystem_id": "compile_case", "page_id": "page_control", "selection_reason": "compile slot", "degrade_reason": ""},
    ]
    state["decomposition_result"] = decomposition_result
    state["architecture_plan"] = architecture_plan
    state["current_step"] = "architecture_planned"
    return state


def _compile_repair_subsystem(state: dict[str, Any]) -> dict[str, Any]:
    state["subsystem_plan_map"] = {
        "compile_case": {
            "subsystem_id": "compile_case",
            "page_id": "page_control",
            "implementation_mode": "atomic_assembly",
            "template_binding": {},
            "selection_reason": "compile repair case",
            "degrade_reason": "",
            "node_instances": [{"logic_id": "src"}, {"logic_id": "dst"}],
            "edges": [],
            "imported_signals": [],
            "exported_signals": [],
            "constraints": [],
            "unresolved_items": [],
            "reasoning": "compile repair case",
        }
    }
    state["current_step"] = "subsystem_planned"
    return state


def _compile_repair_global_assembly(state: dict[str, Any]) -> dict[str, Any]:
    state["execution_plan"] = {"goal": "phase5 compile repair", "nodes": [], "connections": []}
    if not state.get("assembled_graph_ir"):
        state["assembled_graph_ir"] = {
            "graph_ir_version": "2.0",
            "goal": "phase5 compile repair",
            "pages": [{"page_id": "page_control", "label": "控制", "kind": "control", "order": 0}],
            "subflow_definitions": [],
            "node_instances": [
                {"instance_id": "node::src", "logic_id": "src", "input_count": 0, "output_count": 1},
                {"instance_id": "node::dst", "logic_id": "dst", "input_count": 1, "output_count": 1},
            ],
            "edges": [
                {
                    "edge_id": "edge::compile_bad",
                    "from_instance": "node::src",
                    "from_port": 0,
                    "to_instance": "node::dst",
                    "to_port": 2,
                    "signal_id": "signal::compile_bad",
                }
            ],
            "signal_registry": [],
            "layout_hints": {},
            "unresolved_items": [],
            "source_execution_plan": state["execution_plan"],
        }
    state["current_step"] = "global_assembly_completed"
    return state


def _compile_repair_coding(state: dict[str, Any]) -> dict[str, Any]:
    graph_ir = state.get("assembled_graph_ir", {}) or {}
    invalid_port = int(((graph_ir.get("edges", []) or [])[0] or {}).get("to_port", 0) or 0)
    flow_objects = [
        {
            "id": "src1",
            "type": "constInput",
            "wires": [[{"id": "dst1", "port": invalid_port}]],
            "inputs": 0,
            "outputs": 1,
        },
        {
            "id": "dst1",
            "type": "add",
            "wires": [[]],
            "inputs": 1,
            "outputs": 1,
        },
    ]
    state["compiled_artifact"] = {
        "json_text": json.dumps(flow_objects, ensure_ascii=False),
        "flow_objects": flow_objects,
        "id_map": {"node::src": "src1", "node::dst": "dst1"},
        "layout_map": {},
        "compile_report": {
            "page_count": 1,
            "subflow_count": 0,
            "node_count": 2,
            "warnings": [],
        },
    }
    state["generated_code"] = state["compiled_artifact"]["json_text"]
    state["current_step"] = "coding_completed"
    return state


def _compile_repair_verifier(state: dict[str, Any]) -> dict[str, Any]:
    flow_objects = (state.get("compiled_artifact", {}) or {}).get("flow_objects", []) or []
    source_node = flow_objects[0] if flow_objects else {}
    wires = source_node.get("wires", []) or [[]]
    target_port = int((((wires[0] or [{}])[0] or {}).get("port", 0)) or 0)
    if target_port >= 1:
        report = {
            "status": "retryable_error",
            "repair_scope": "compile",
            "issue_summary": "编译连线端口越界。",
            "issues": [
                {
                    "issue_id": "CP-001",
                    "scope": "compile",
                    "target_id": "src1",
                    "rule_id": "compile.wire.port.range",
                    "message": f"wire 引用了越界端口: dst1[{target_port}] / inputs=1",
                    "repair_payload": {
                        "source_real_id": "src1",
                        "target_real_id": "dst1",
                        "invalid_target_port": target_port,
                        "target_input_count": 1,
                    },
                }
            ],
            "warnings": [],
            "metrics": {"invalid_port_refs": 1},
        }
    else:
        report = {
            "status": "passed",
            "repair_scope": "none",
            "issue_summary": "修复后通过。",
            "issues": [],
            "warnings": [],
            "metrics": {"invalid_port_refs": 0},
        }
    return _set_verification_report(state, report)


def _budget_exhausted_analysis(state: dict[str, Any]) -> dict[str, Any]:
    return _set_analysis_state(
        state,
        "Phase 5 budget exhausted",
        retry_counts_by_scope={"planning": 0, "assembly": 0, "compile": 2},
    )


def _budget_exhausted_retrieval(state: dict[str, Any]) -> dict[str, Any]:
    return _set_retrieval_state(state)


def _budget_exhausted_architecture(state: dict[str, Any]) -> dict[str, Any]:
    decomposition_result, architecture_plan = _base_architecture_payload("phase5 budget exhausted")
    decomposition_result["planning_order"] = ["budget_case"]
    decomposition_result["subsystem_descriptors"] = [{"subsystem_id": "budget_case", "imports": [], "exports": []}]
    architecture_plan["subsystem_slots"] = [
        {"subsystem_id": "budget_case", "page_id": "page_control", "selection_reason": "budget slot", "degrade_reason": ""},
    ]
    state["decomposition_result"] = decomposition_result
    state["architecture_plan"] = architecture_plan
    state["current_step"] = "architecture_planned"
    return state


def _budget_exhausted_subsystem(state: dict[str, Any]) -> dict[str, Any]:
    state["subsystem_plan_map"] = {
        "budget_case": {
            "subsystem_id": "budget_case",
            "page_id": "page_control",
            "implementation_mode": "atomic_assembly",
            "template_binding": {},
            "selection_reason": "budget exhausted",
            "degrade_reason": "",
            "node_instances": [{"logic_id": "src"}, {"logic_id": "dst"}],
            "edges": [],
            "imported_signals": [],
            "exported_signals": [],
            "constraints": [],
            "unresolved_items": [],
            "reasoning": "budget exhausted case",
        }
    }
    state["current_step"] = "subsystem_planned"
    return state


def _budget_exhausted_global_assembly(state: dict[str, Any]) -> dict[str, Any]:
    state["execution_plan"] = {"goal": "phase5 budget exhausted", "nodes": [], "connections": []}
    state["assembled_graph_ir"] = {
        "graph_ir_version": "2.0",
        "goal": "phase5 budget exhausted",
        "pages": [{"page_id": "page_control", "label": "控制", "kind": "control", "order": 0}],
        "subflow_definitions": [],
        "node_instances": [
            {"instance_id": "node::src", "logic_id": "src", "input_count": 0, "output_count": 1},
            {"instance_id": "node::dst", "logic_id": "dst", "input_count": 1, "output_count": 1},
        ],
        "edges": [],
        "signal_registry": [],
        "layout_hints": {},
        "unresolved_items": [],
        "source_execution_plan": state["execution_plan"],
    }
    state["current_step"] = "global_assembly_completed"
    return state


def _budget_exhausted_coding(state: dict[str, Any]) -> dict[str, Any]:
    state["compiled_artifact"] = _simple_compiled_artifact(node_count=2)
    state["generated_code"] = state["compiled_artifact"]["json_text"]
    state["current_step"] = "coding_completed"
    return state


def _budget_exhausted_verifier(state: dict[str, Any]) -> dict[str, Any]:
    report = {
        "status": "retryable_error",
        "repair_scope": "compile",
        "issue_summary": "达到 compile scope 重试上限。",
        "issues": [
            {
                "issue_id": "CP-BUDGET-001",
                "scope": "compile",
                "target_id": "src1",
                "rule_id": "compile.wire.port.range",
                "message": "wire 引用了越界端口: dst1[2] / inputs=1",
                "repair_payload": {
                    "source_real_id": "src1",
                    "target_real_id": "dst1",
                    "invalid_target_port": 2,
                    "target_input_count": 1,
                },
            }
        ],
        "warnings": [],
        "metrics": {"invalid_port_refs": 1},
    }
    return _set_verification_report(state, report)


def _multi_round_analysis(state: dict[str, Any]) -> dict[str, Any]:
    return _set_analysis_state(state, "Phase 5 multi-round repair")


def _multi_round_retrieval(state: dict[str, Any]) -> dict[str, Any]:
    return _set_retrieval_state(state)


def _multi_round_architecture(state: dict[str, Any]) -> dict[str, Any]:
    return _planning_repair_architecture(state)


def _multi_round_subsystem(state: dict[str, Any]) -> dict[str, Any]:
    owner = _shared_signal_owner(state)
    exported_signals = []
    if owner == "supply_fan_ctrl":
        exported_signals = [
            {
                "signal_name": "supply_fan_available_flag",
                "signal_key": "supply_fan_available_flag",
                "canonical_signal_key": "supply_fan_available",
                "binding_kind": "shared_signal",
                "allowed_external": False,
            }
        ]
    state["subsystem_plan_map"] = {
        "supply_fan_ctrl": {
            "subsystem_id": "supply_fan_ctrl",
            "page_id": "page_control",
            "implementation_mode": "reuse_template",
            "template_binding": {"template_id": "fan_template"},
            "selection_reason": "multi-round fan",
            "degrade_reason": "",
            "node_instances": [{"logic_id": "fan_main"}],
            "edges": [],
            "imported_signals": [],
            "exported_signals": exported_signals,
            "constraints": [],
            "unresolved_items": [],
            "reasoning": "multi-round fan",
        },
        "heater_ctrl": {
            "subsystem_id": "heater_ctrl",
            "page_id": "page_control",
            "implementation_mode": "atomic_assembly",
            "template_binding": {},
            "selection_reason": "multi-round heater",
            "degrade_reason": "",
            "node_instances": [{"logic_id": "src"}, {"logic_id": "dst"}],
            "edges": [],
            "imported_signals": [
                {
                    "signal_name": "supply_fan_available_flag",
                    "signal_key": "supply_fan_available_flag",
                    "canonical_signal_key": "supply_fan_available",
                    "binding_kind": "shared_signal",
                    "allowed_external": False,
                }
            ],
            "exported_signals": [],
            "constraints": [],
            "unresolved_items": [],
            "reasoning": "multi-round heater",
        },
    }
    state["current_step"] = "subsystem_planned"
    return state


def _multi_round_global_assembly(state: dict[str, Any]) -> dict[str, Any]:
    owner = _shared_signal_owner(state)
    if owner != "supply_fan_ctrl":
        return _planning_repair_global_assembly(state)
    state["execution_plan"] = {"goal": "phase5 multi-round repair", "nodes": [], "connections": []}
    state["assembled_graph_ir"] = {
        "graph_ir_version": "2.0",
        "goal": "phase5 multi-round repair",
        "pages": [{"page_id": "page_control", "label": "控制", "kind": "control", "order": 0}],
        "subflow_definitions": [],
        "node_instances": [
            {"instance_id": "node::src", "logic_id": "src", "input_count": 0, "output_count": 1},
            {"instance_id": "node::dst", "logic_id": "dst", "input_count": 1, "output_count": 1},
        ],
        "edges": [
            {
                "edge_id": "edge::multi_round_bad",
                "from_instance": "node::src",
                "from_port": 0,
                "to_instance": "node::dst",
                "to_port": 2,
                "signal_id": "signal::multi_round_bad",
            }
        ],
        "signal_registry": [],
        "layout_hints": {},
        "unresolved_items": [],
        "source_execution_plan": state["execution_plan"],
    }
    state["current_step"] = "global_assembly_completed"
    return state


def _multi_round_coding(state: dict[str, Any]) -> dict[str, Any]:
    graph_ir = state.get("assembled_graph_ir", {}) or {}
    if graph_ir.get("unresolved_items"):
        state["compiled_artifact"] = _simple_compiled_artifact(node_count=2)
    else:
        _compile_repair_coding(state)
    state["generated_code"] = state["compiled_artifact"]["json_text"]
    state["current_step"] = "coding_completed"
    return state


def _multi_round_verifier(state: dict[str, Any]) -> dict[str, Any]:
    unresolved_items = (state.get("assembled_graph_ir", {}) or {}).get("unresolved_items", []) or []
    if unresolved_items:
        return _planning_repair_verifier(state)
    return _compile_repair_verifier(state)


def build_default_cases() -> list[Phase5Case]:
    return [
        Phase5Case(
            case_id="success_accept",
            name="成功通过",
            query="为 AHU 生成送风机标准控制",
            expected_verification_status="passed",
            expected_route_decision="accept",
            expected_repair_scope="none",
            build_node_factories=lambda: {
                "AnalysisAgent": _node_factory(_success_analysis),
                "RetrievalAgent": _node_factory(_success_retrieval),
                "ArchitecturePlanner": _node_factory(_success_architecture),
                "SubsystemPlanner": _node_factory(_success_subsystem),
                "GlobalAssembler": _node_factory(_success_global_assembly),
                "CodingAgent": _node_factory(_success_coding),
                "VerifierAgent": _node_factory(_success_verifier),
            },
        ),
        Phase5Case(
            case_id="reject_ambiguous_shared_signal",
            name="稳定拒绝",
            query="为 AHU 生成送风机与电加热联动控制，但共享信号 exporter 歧义未收敛",
            expected_verification_status="retryable_error",
            expected_route_decision="reject",
            expected_repair_scope="planning",
            build_node_factories=lambda: {
                "AnalysisAgent": _node_factory(_ambiguous_reject_analysis),
                "RetrievalAgent": _node_factory(_ambiguous_reject_retrieval),
                "ArchitecturePlanner": _node_factory(_ambiguous_reject_architecture),
                "SubsystemPlanner": _node_factory(_ambiguous_reject_subsystem),
                "GlobalAssembler": _node_factory(_ambiguous_reject_global_assembly),
                "CodingAgent": _node_factory(_ambiguous_reject_coding),
                "VerifierAgent": _node_factory(_ambiguous_reject_verifier),
            },
            expected_reject_reason="ambiguous_shared_signal_unresolved",
            expected_repair_reject_category="ambiguous_shared_signal",
            expected_min_repair_rounds=1,
            expected_unresolved_types=("ambiguous_shared_signal",),
        ),
        Phase5Case(
            case_id="repair_planning_success",
            name="Planning Repair 成功",
            query="为 AHU 生成送风机可用信号联动电加热控制",
            expected_verification_status="passed",
            expected_route_decision="accept",
            expected_repair_scope="none",
            build_node_factories=lambda: {
                "AnalysisAgent": _node_factory(_planning_repair_analysis),
                "RetrievalAgent": _node_factory(_planning_repair_retrieval),
                "ArchitecturePlanner": _node_factory(_planning_repair_architecture),
                "SubsystemPlanner": _node_factory(_planning_repair_subsystem),
                "GlobalAssembler": _node_factory(_planning_repair_global_assembly),
                "CodingAgent": _node_factory(_planning_repair_coding),
                "VerifierAgent": _node_factory(_planning_repair_verifier),
            },
            expected_min_repair_rounds=1,
        ),
        Phase5Case(
            case_id="repair_assembly_success",
            name="Assembly Repair 成功",
            query="为 AHU 生成局部边端点缺失后可自动修补的场景",
            expected_verification_status="passed",
            expected_route_decision="accept",
            expected_repair_scope="none",
            build_node_factories=lambda: {
                "AnalysisAgent": _node_factory(_assembly_repair_analysis),
                "RetrievalAgent": _node_factory(_assembly_repair_retrieval),
                "ArchitecturePlanner": _node_factory(_assembly_repair_architecture),
                "SubsystemPlanner": _node_factory(_assembly_repair_subsystem),
                "GlobalAssembler": _node_factory(_assembly_repair_global_assembly),
                "CodingAgent": _node_factory(_assembly_repair_coding),
                "VerifierAgent": _node_factory(_assembly_repair_verifier),
            },
            expected_min_repair_rounds=1,
        ),
        Phase5Case(
            case_id="repair_compile_success",
            name="Compile Repair 成功",
            query="为 AHU 生成编译连线端口越界后可自动修补的场景",
            expected_verification_status="passed",
            expected_route_decision="accept",
            expected_repair_scope="none",
            build_node_factories=lambda: {
                "AnalysisAgent": _node_factory(_compile_repair_analysis),
                "RetrievalAgent": _node_factory(_compile_repair_retrieval),
                "ArchitecturePlanner": _node_factory(_compile_repair_architecture),
                "SubsystemPlanner": _node_factory(_compile_repair_subsystem),
                "GlobalAssembler": _node_factory(_compile_repair_global_assembly),
                "CodingAgent": _node_factory(_compile_repair_coding),
                "VerifierAgent": _node_factory(_compile_repair_verifier),
            },
            expected_min_repair_rounds=1,
        ),
        Phase5Case(
            case_id="reject_budget_exhausted",
            name="预算耗尽",
            query="为 AHU 生成 compile scope 已耗尽预算的场景",
            expected_verification_status="retryable_error",
            expected_route_decision="reject",
            expected_repair_scope="compile",
            build_node_factories=lambda: {
                "AnalysisAgent": _node_factory(_budget_exhausted_analysis),
                "RetrievalAgent": _node_factory(_budget_exhausted_retrieval),
                "ArchitecturePlanner": _node_factory(_budget_exhausted_architecture),
                "SubsystemPlanner": _node_factory(_budget_exhausted_subsystem),
                "GlobalAssembler": _node_factory(_budget_exhausted_global_assembly),
                "CodingAgent": _node_factory(_budget_exhausted_coding),
                "VerifierAgent": _node_factory(_budget_exhausted_verifier),
            },
            expected_reject_reason="retry_budget_exhausted",
            expected_repair_reject_category="budget_exhausted",
        ),
    ]


def build_multi_round_case() -> Phase5Case:
    return Phase5Case(
        case_id="multi_round_repair",
        name="多轮 Repair",
        query="为 AHU 生成先 planning repair 再 compile repair 的场景",
        expected_verification_status="passed",
        expected_route_decision="accept",
        expected_repair_scope="none",
        build_node_factories=lambda: {
            "AnalysisAgent": _node_factory(_multi_round_analysis),
            "RetrievalAgent": _node_factory(_multi_round_retrieval),
            "ArchitecturePlanner": _node_factory(_multi_round_architecture),
            "SubsystemPlanner": _node_factory(_multi_round_subsystem),
            "GlobalAssembler": _node_factory(_multi_round_global_assembly),
            "CodingAgent": _node_factory(_multi_round_coding),
            "VerifierAgent": _node_factory(_multi_round_verifier),
        },
        expected_min_repair_rounds=2,
    )


def _read_trace_summary(trace_info: dict[str, Any]) -> dict[str, Any]:
    summary_json = Path(str(trace_info.get("summary_json", "")).strip())
    if not summary_json.exists():
        return {}
    return json.loads(summary_json.read_text(encoding="utf-8"))


def _compare_expected(case: Phase5Case, actual: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if actual["verification_status"] != case.expected_verification_status:
        failures.append(
            f"verification_status expected={case.expected_verification_status} actual={actual['verification_status']}"
        )
    if actual["route_decision"] != case.expected_route_decision:
        failures.append(
            f"route_decision expected={case.expected_route_decision} actual={actual['route_decision']}"
        )
    if actual["repair_scope"] != case.expected_repair_scope:
        failures.append(
            f"repair_scope expected={case.expected_repair_scope} actual={actual['repair_scope']}"
        )
    if case.expected_reject_reason and actual["reject_reason"] != case.expected_reject_reason:
        failures.append(
            f"reject_reason expected={case.expected_reject_reason} actual={actual['reject_reason']}"
        )
    if case.expected_repair_reject_category and actual["repair_reject_category"] != case.expected_repair_reject_category:
        failures.append(
            "repair_reject_category "
            f"expected={case.expected_repair_reject_category} actual={actual['repair_reject_category']}"
        )
    if actual["repair_round_count"] < case.expected_min_repair_rounds:
        failures.append(
            f"repair_round_count expected>={case.expected_min_repair_rounds} actual={actual['repair_round_count']}"
        )
    if case.expected_unresolved_types:
        actual_unresolved = set(actual["unresolved_item_types"])
        missing = [item for item in case.expected_unresolved_types if item not in actual_unresolved]
        if missing:
            failures.append(
                f"unresolved_item_types missing expected entries: {', '.join(missing)}"
            )
    return len(failures) == 0, failures


def run_case(
    case: Phase5Case,
    *,
    trace_output_root: str | Path | None = None,
) -> dict[str, Any]:
    node_factories = case.build_node_factories()
    with ExitStack() as stack:
        if trace_output_root is not None:
            stack.enter_context(
                patch.object(workflow_trace, "TRACE_OUTPUT_ROOT", str(Path(trace_output_root)))
            )
        for attribute_name, factory in node_factories.items():
            stack.enter_context(patch.object(workflow_trace, attribute_name, factory))
        result = workflow_trace.run_workflow(case.query)

    verification_report = result.get("verification_report", {}) or {}
    route_decision = result.get("route_decision", {}) or {}
    trace_info = (result.get("final_output", {}) or {}).get("workflow_trace", {}) or {}
    trace_summary = _read_trace_summary(trace_info)
    actual = {
        "verification_status": str(verification_report.get("status", "")).strip(),
        "repair_scope": str(verification_report.get("repair_scope", "")).strip(),
        "route_decision": str(route_decision.get("decision", "")).strip(),
        "reject_reason": str(route_decision.get("reason", "")).strip() if str(route_decision.get("decision", "")).strip() == "reject" else "",
        "repair_round_count": int(trace_summary.get("repair_round_count", len(result.get("repair_history", []) or [])) or 0),
        "repair_reject_category": str(trace_summary.get("repair_reject_category", "")).strip(),
        "unresolved_item_types": list(trace_summary.get("unresolved_item_types", []) or []),
        "planning_unresolved_by_type": dict(trace_summary.get("planning_unresolved_by_type", {}) or {}),
        "ambiguous_signal_count": int(trace_summary.get("ambiguous_signal_count", 0) or 0),
        "trace_dir": str(trace_info.get("trace_dir", "")).strip(),
        "trace_summary_json": str(trace_info.get("summary_json", "")).strip(),
        "trace_summary_md": str(trace_info.get("summary_md", "")).strip(),
    }
    passed, failures = _compare_expected(case, actual)
    return {
        "case_id": case.case_id,
        "name": case.name,
        "query": case.query,
        "passed": passed,
        "failures": failures,
        "expected": {
            "verification_status": case.expected_verification_status,
            "repair_scope": case.expected_repair_scope,
            "route_decision": case.expected_route_decision,
            "reject_reason": case.expected_reject_reason,
            "repair_reject_category": case.expected_repair_reject_category,
            "min_repair_rounds": case.expected_min_repair_rounds,
            "unresolved_types": list(case.expected_unresolved_types),
        },
        "actual": actual,
    }


def _write_suite_markdown(run_dir: Path, suite_summary: dict[str, Any]) -> Path:
    summary_md = run_dir / "phase5_query_suite_summary.md"
    lines = [
        "# Phase 5 Query Suite",
        "",
        f"- 生成时间：{suite_summary['generated_at']}",
        f"- case_count：{suite_summary['case_count']}",
        f"- passed_count：{suite_summary['passed_count']}",
        f"- failed_count：{suite_summary['failed_count']}",
        f"- all_passed：`{suite_summary['all_passed']}`",
        "",
    ]
    for item in suite_summary["results"]:
        actual = item["actual"]
        lines.extend(
            [
                f"## {item['name']} (`{item['case_id']}`)",
                f"- query: `{item['query']}`",
                f"- passed: `{item['passed']}`",
                f"- verification_status: `{actual['verification_status']}`",
                f"- repair_scope: `{actual['repair_scope']}`",
                f"- route_decision: `{actual['route_decision']}`",
                f"- reject_reason: `{actual['reject_reason'] or 'N/A'}`",
                f"- repair_round_count: `{actual['repair_round_count']}`",
                f"- repair_reject_category: `{actual['repair_reject_category'] or 'N/A'}`",
                f"- planning_unresolved_by_type: `{json.dumps(actual['planning_unresolved_by_type'], ensure_ascii=False, sort_keys=True)}`",
                f"- ambiguous_signal_count: `{actual['ambiguous_signal_count']}`",
                f"- unresolved_item_types: `{', '.join(actual['unresolved_item_types']) if actual['unresolved_item_types'] else 'none'}`",
                f"- trace_dir: `{actual['trace_dir']}`",
                f"- trace_summary_json: `{actual['trace_summary_json']}`",
                f"- trace_summary_md: `{actual['trace_summary_md']}`",
            ]
        )
        if item["failures"]:
            lines.append(f"- failures: `{'; '.join(item['failures'])}`")
        lines.append("")
    summary_md.write_text("\n".join(lines), encoding="utf-8")
    return summary_md


def run_suite(
    cases: list[Phase5Case] | None = None,
    *,
    output_root: str | Path | None = None,
    trace_output_root: str | Path | None = None,
) -> dict[str, Any]:
    selected_cases = list(cases or build_default_cases())
    output_root_path = Path(output_root) if output_root is not None else OUTPUT_ROOT
    run_dir = output_root_path / f"suite_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    run_dir.mkdir(parents=True, exist_ok=True)

    results = [
        run_case(case, trace_output_root=trace_output_root)
        for case in selected_cases
    ]
    suite_summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "case_count": len(results),
        "passed_count": sum(1 for item in results if item["passed"]),
        "failed_count": sum(1 for item in results if not item["passed"]),
        "all_passed": all(item["passed"] for item in results),
        "results": results,
    }

    summary_json = run_dir / "phase5_query_suite_summary.json"
    summary_json.write_text(json.dumps(suite_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_md = _write_suite_markdown(run_dir, suite_summary)
    suite_summary["summary_json"] = str(summary_json.resolve())
    suite_summary["summary_md"] = str(summary_md.resolve())
    suite_summary["run_dir"] = str(run_dir.resolve())
    return suite_summary


def main() -> int:
    suite_summary = run_suite()
    print(f"Phase 5 query suite summary written to: {suite_summary['summary_md']}")
    for item in suite_summary["results"]:
        print(
            json.dumps(
                {
                    "case_id": item["case_id"],
                    "passed": item["passed"],
                    "verification_status": item["actual"]["verification_status"],
                    "repair_scope": item["actual"]["repair_scope"],
                    "route_decision": item["actual"]["route_decision"],
                    "reject_reason": item["actual"]["reject_reason"],
                    "repair_round_count": item["actual"]["repair_round_count"],
                    "trace_dir": item["actual"]["trace_dir"],
                },
                ensure_ascii=False,
            )
        )
    return 0 if suite_summary["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
