from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.repair_agent import RepairAgent
import workflow


def _planning_state() -> dict:
    state = workflow.build_initial_state("为 AHU 生成送风机与电加热联动控制")
    state["requirement_spec"] = {
        "signals": {"inputs": [], "outputs": [], "software_points": [], "alarm_points": []},
        "global_modes": [],
    }
    state["decomposition_result"] = {
        "pages": [],
        "subsystem_descriptors": [
            {
                "subsystem_id": "supply_fan_ctrl",
                "imports": [],
                "exports": ["supply_fan_available_flag"],
            },
            {
                "subsystem_id": "heater_ctrl",
                "imports": ["supply_fan_available_flag"],
                "exports": ["heater_enable"],
            },
        ],
        "shared_signal_registry": [
            {
                "signal_name": "supply_fan_available_flag",
                "signal_key": "supply_fan_available_flag",
                "owner_subsystem_id": "",
                "allowed_external": False,
                "required_exporter_count": 1,
                "consumers": ["heater_ctrl"],
                "source_reason": "planner projected consumer without owner",
            }
        ],
        "template_needs": [],
        "planning_order": ["supply_fan_ctrl", "heater_ctrl"],
        "warnings": [],
    }
    state["architecture_plan"] = {
        "goal": "fan heater link",
        "pages": [],
        "subsystem_slots": [],
        "shared_signal_registry": [
            {
                "signal_name": "supply_fan_available_flag",
                "signal_key": "supply_fan_available_flag",
                "owner_subsystem_id": "",
                "allowed_external": False,
                "required_exporter_count": 1,
                "consumers": ["heater_ctrl"],
                "source_reason": "planner projected consumer without owner",
            }
        ],
        "global_constraints": [],
        "naming_strategy": {},
        "layout_strategy": {},
        "pattern_bindings": [],
        "warnings": [],
    }
    state["subsystem_plan_map"] = {
        "supply_fan_ctrl": {"exported_signals": []},
        "heater_ctrl": {"imported_signals": [{"signal_name": "supply_fan_available_flag"}]},
    }
    state["assembled_graph_ir"] = {"unresolved_items": [{"type": "synthetic_shared_signal_source"}]}
    state["compiled_artifact"] = {"json_text": "[]"}
    state["verification_report"] = {
        "status": "retryable_error",
        "repair_scope": "planning",
        "issues": [
            {
                "issue_id": "IR-001",
                "scope": "planning",
                "target_id": "supply_fan_available_flag",
                "rule_id": "ir.unresolved.synthetic_shared_signal_source",
                "message": "Shared signal supply_fan_available_flag has no real exporter.",
            }
        ],
        "warnings": [],
        "metrics": {},
    }
    state["route_decision"] = {
        "decision": "planning_repair",
        "repair_scope": "planning",
        "next_node": "repair_agent",
        "reason": "planning_retry_allowed",
        "issue_ids": ["IR-001"],
        "retry_exhausted": False,
        "retry_count_for_scope": 0,
        "retry_budget_for_scope": 2,
    }
    state["final_output"] = {"verification_report": state["verification_report"]}
    return state


def _assembly_state() -> dict:
    state = workflow.build_initial_state("assembly repair")
    state["subsystem_plan_map"] = {
        "heater_ctrl": {
            "subsystem_id": "heater_ctrl",
            "page_id": "page_control",
            "node_instances": [{"logic_id": "heater_main"}],
            "edges": [
                {
                    "from_node": "ghost_source",
                    "from_port": 0,
                    "to_node": "heater_main",
                    "to_port": 0,
                    "signal_name": "schedule_enable",
                }
            ],
            "unresolved_items": [],
        }
    }
    state["assembled_graph_ir"] = {"unresolved_items": [{"type": "missing_local_edge_endpoint"}]}
    state["compiled_artifact"] = {"json_text": "[]"}
    state["verification_report"] = {
        "status": "retryable_error",
        "repair_scope": "assembly",
        "issues": [
            {
                "issue_id": "IR-010",
                "scope": "assembly",
                "target_id": "heater_ctrl",
                "rule_id": "ir.unresolved.missing_local_edge_endpoint",
                "message": "Local edge references missing nodes.",
            }
        ],
        "warnings": [],
        "metrics": {},
    }
    state["route_decision"] = {
        "decision": "assembly_repair",
        "repair_scope": "assembly",
        "next_node": "repair_agent",
        "reason": "assembly_retry_allowed",
        "issue_ids": ["IR-010"],
        "retry_exhausted": False,
        "retry_count_for_scope": 0,
        "retry_budget_for_scope": 2,
    }
    state["final_output"] = {"verification_report": state["verification_report"]}
    return state


def _compile_state() -> dict:
    state = workflow.build_initial_state("compile repair")
    state["assembled_graph_ir"] = {
        "node_instances": [
            {"instance_id": "node::src", "input_count": 0, "output_count": 1},
            {"instance_id": "node::dst", "input_count": 1, "output_count": 1},
        ],
        "edges": [
            {
                "edge_id": "edge::1",
                "from_instance": "node::src",
                "from_port": 0,
                "to_instance": "node::dst",
                "to_port": 2,
                "signal_id": "signal::1",
            }
        ],
    }
    state["compiled_artifact"] = {
        "json_text": "[]",
        "id_map": {"node::src": "src1", "node::dst": "dst1"},
        "flow_objects": [
            {"id": "src1", "type": "constInput", "wires": [[{"id": "dst1", "port": 2}]], "inputs": 0, "outputs": 1},
            {"id": "dst1", "type": "add", "wires": [[]], "inputs": 1, "outputs": 1},
        ],
        "compile_report": {"page_count": 1, "subflow_count": 0, "node_count": 2, "warnings": []},
    }
    state["verification_report"] = {
        "status": "retryable_error",
        "repair_scope": "compile",
        "issues": [
            {
                "issue_id": "CP-001",
                "scope": "compile",
                "target_id": "src1",
                "rule_id": "compile.wire.port.range",
                "message": "wire 引用了越界端口: dst1[2] / inputs=1",
            }
        ],
        "warnings": [],
        "metrics": {"invalid_port_refs": 1},
    }
    state["route_decision"] = {
        "decision": "compile_repair",
        "repair_scope": "compile",
        "next_node": "repair_agent",
        "reason": "compile_retry_allowed",
        "issue_ids": ["CP-001"],
        "retry_exhausted": False,
        "retry_count_for_scope": 0,
        "retry_budget_for_scope": 2,
    }
    state["final_output"] = {"verification_report": state["verification_report"]}
    return state


def _unsupported_state() -> dict:
    state = workflow.build_initial_state("unsupported repair")
    state["verification_report"] = {
        "status": "retryable_error",
        "repair_scope": "planning",
        "issues": [
            {
                "issue_id": "PL-999",
                "scope": "planning",
                "target_id": "supply_fan_ctrl",
                "rule_id": "template_input_interface_mismatch",
                "message": "template mismatch",
            }
        ],
        "warnings": [],
        "metrics": {},
    }
    state["route_decision"] = {
        "decision": "planning_repair",
        "repair_scope": "planning",
        "next_node": "repair_agent",
        "reason": "planning_retry_allowed",
        "issue_ids": ["PL-999"],
        "retry_exhausted": False,
        "retry_count_for_scope": 0,
        "retry_budget_for_scope": 2,
    }
    return state


class RepairAgentTests(unittest.TestCase):
    def test_planning_repair_rebinds_shared_signal_owner_and_invalidates_downstream(self):
        state = _planning_state()

        result = RepairAgent()(state)

        signal_entry = result["architecture_plan"]["shared_signal_registry"][0]
        self.assertEqual(signal_entry["owner_subsystem_id"], "supply_fan_ctrl")
        self.assertEqual(result["decomposition_result"]["shared_signal_registry"][0]["owner_subsystem_id"], "supply_fan_ctrl")
        self.assertEqual(result["architecture_plan"]["global_constraints"][0]["value"], "supply_fan_ctrl")
        self.assertEqual(result["repair_context"]["resume_node"], "subsystem_planning")
        self.assertEqual(result["route_decision"]["next_node"], "subsystem_planning")
        self.assertEqual(result["retry_counts_by_scope"]["planning"], 1)
        self.assertEqual(result["retry_count"], 1)
        self.assertEqual(result["subsystem_plan_map"], {})
        self.assertEqual(result["verification_report"], {})
        self.assertEqual(result["final_output"], {})

    def test_assembly_repair_removes_invalid_local_edges(self):
        state = _assembly_state()

        result = RepairAgent()(state)

        subsystem_plan = result["subsystem_plan_map"]["heater_ctrl"]
        self.assertEqual(subsystem_plan["edges"], [])
        self.assertEqual(subsystem_plan["unresolved_items"][0]["severity"], "warning")
        self.assertEqual(result["repair_context"]["resume_node"], "global_assembly")
        self.assertEqual(result["route_decision"]["next_node"], "global_assembly")
        self.assertEqual(result["retry_counts_by_scope"]["assembly"], 1)
        self.assertEqual(result["assembled_graph_ir"], {})
        self.assertEqual(result["compiled_artifact"], {})

    def test_compile_repair_clamps_target_port_and_clears_compiled_outputs(self):
        state = _compile_state()

        result = RepairAgent()(state)

        self.assertEqual(result["assembled_graph_ir"]["edges"][0]["to_port"], 0)
        self.assertEqual(result["repair_context"]["resume_node"], "coding")
        self.assertEqual(result["route_decision"]["next_node"], "coding")
        self.assertEqual(result["retry_counts_by_scope"]["compile"], 1)
        self.assertEqual(result["compiled_artifact"], {})
        self.assertEqual(result["verification_report"], {})
        self.assertEqual(result["final_output"], {})

    def test_unsupported_issue_is_rejected_without_resume(self):
        state = _unsupported_state()

        result = RepairAgent()(state)

        self.assertEqual(result["route_decision"]["decision"], "reject")
        self.assertEqual(result["route_decision"]["next_node"], "END")
        self.assertEqual(result["route_decision"]["reason"], "unsupported_repair_issue")
        self.assertEqual(result["repair_history"][0]["result"], "rejected")
        self.assertEqual(result["retry_counts_by_scope"]["planning"], 1)
        self.assertEqual(result["current_step"], "repair_rejected")


if __name__ == "__main__":
    unittest.main()
