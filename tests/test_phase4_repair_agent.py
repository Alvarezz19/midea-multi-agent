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
                "imports": [],
                "exports": ["supply_fan_available_flag"],
            },
            {
                "subsystem_id": "heater_ctrl",
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
                "imports": ["supply_fan_available_flag"],
                "exports": ["heater_enable"],
            },
        ],
        "shared_signal_registry": [
            {
                "signal_name": "supply_fan_available_flag",
                "signal_key": "supply_fan_available",
                "canonical_signal_key": "supply_fan_available",
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
                "signal_key": "supply_fan_available",
                "canonical_signal_key": "supply_fan_available",
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
                "repair_payload": {
                    "signal_name": "supply_fan_available_flag",
                    "canonical_signal_key": "supply_fan_available",
                    "binding_kind": "shared_signal",
                    "allowed_external": False,
                    "candidate_exporters": ["supply_fan_ctrl"],
                    "consumer_subsystem_ids": ["heater_ctrl"],
                },
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


def _planning_external_state() -> dict:
    state = workflow.build_initial_state("为 AHU 生成送风机标准控制")
    state["requirement_spec"] = {
        "signals": {"inputs": [], "outputs": [], "software_points": [], "alarm_points": []},
        "global_modes": [],
    }
    state["decomposition_result"] = {
        "pages": [],
        "subsystem_descriptors": [
            {
                "subsystem_id": "supply_fan_ctrl",
                "imports": ["送风机运行状态"],
                "exports": ["送风机运行标志"],
                "interface_bindings": [
                    {
                        "signal_name": "送风机运行状态",
                        "signal_key": "送风机运行状态",
                        "canonical_signal_key": "supply_fan_run_state",
                        "direction": "input",
                        "binding_kind": "shared_signal",
                        "allowed_external": False,
                        "owner_subsystem_id": "",
                        "port_index": 0,
                    },
                    {
                        "signal_name": "送风机运行标志",
                        "signal_key": "送风机运行标志",
                        "canonical_signal_key": "supply_fan_run_state",
                        "direction": "output",
                        "binding_kind": "subsystem_output",
                        "allowed_external": False,
                        "owner_subsystem_id": "",
                        "port_index": 0,
                    },
                ],
            }
        ],
        "shared_signal_registry": [
            {
                "signal_name": "送风机运行状态",
                "signal_key": "supply_fan_run_state",
                "canonical_signal_key": "supply_fan_run_state",
                "owner_subsystem_id": "",
                "allowed_external": False,
                "required_exporter_count": 1,
                "consumers": ["supply_fan_ctrl"],
                "source_reason": "planner projected consumer without owner",
            }
        ],
        "template_needs": [],
        "planning_order": ["supply_fan_ctrl"],
        "warnings": [],
    }
    state["architecture_plan"] = {
        "goal": "fan standard",
        "pages": [],
        "subsystem_slots": [],
        "shared_signal_registry": [
            {
                "signal_name": "送风机运行状态",
                "signal_key": "supply_fan_run_state",
                "canonical_signal_key": "supply_fan_run_state",
                "owner_subsystem_id": "",
                "allowed_external": False,
                "required_exporter_count": 1,
                "consumers": ["supply_fan_ctrl"],
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
        "supply_fan_ctrl": {"imported_signals": [{"signal_name": "送风机运行状态", "binding_kind": "shared_signal"}]},
    }
    state["assembled_graph_ir"] = {"unresolved_items": [{"type": "synthetic_shared_signal_source"}]}
    state["compiled_artifact"] = {"json_text": "[]"}
    state["verification_report"] = {
        "status": "retryable_error",
        "repair_scope": "planning",
        "issues": [
            {
                "issue_id": "IR-EXT-001",
                "scope": "planning",
                "target_id": "送风机运行状态",
                "rule_id": "ir.unresolved.synthetic_shared_signal_source",
                "message": "Shared signal 送风机运行状态 has no real exporter.",
                "repair_payload": {
                    "signal_name": "送风机运行状态",
                    "canonical_signal_key": "supply_fan_run_state",
                    "binding_kind": "external_input",
                    "allowed_external": True,
                    "candidate_exporters": [],
                    "consumer_subsystem_ids": ["supply_fan_ctrl"],
                },
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
        "issue_ids": ["IR-EXT-001"],
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
                {
                    "edge_id": "edge::ghost_keep",
                    "from_node": "heater_source",
                    "from_port": 0,
                    "to_node": "ghost_target",
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


def _planning_ambiguous_converge_state() -> dict:
    state = _planning_state()
    state["decomposition_result"]["subsystem_descriptors"].append(
        {
            "subsystem_id": "backup_ctrl",
            "interface_bindings": [],
            "imports": [],
            "exports": [],
        }
    )
    state["verification_report"]["issues"] = [
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
                "candidate_exporters": ["supply_fan_ctrl", "backup_ctrl"],
                "consumer_subsystem_ids": ["heater_ctrl"],
                "resolution_status": "ambiguous",
            },
        }
    ]
    state["route_decision"]["issue_ids"] = ["IR-AMB-001"]
    return state


def _planning_ambiguous_unresolved_state() -> dict:
    state = _planning_ambiguous_converge_state()
    state["decomposition_result"]["subsystem_descriptors"][-1] = {
        "subsystem_id": "backup_ctrl",
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
        "imports": [],
        "exports": ["supply_fan_available_flag"],
    }
    state["subsystem_plan_map"]["backup_ctrl"] = {
        "exported_signals": [{"signal_name": "supply_fan_available_flag"}]
    }
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
                "message": "legacy message should not be required",
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

    def test_planning_repair_reclassifies_signal_as_external(self):
        state = _planning_external_state()

        result = RepairAgent()(state)

        signal_entry = result["architecture_plan"]["shared_signal_registry"][0]
        self.assertTrue(signal_entry["allowed_external"])
        self.assertEqual(signal_entry["required_exporter_count"], 0)
        descriptor_binding = result["decomposition_result"]["subsystem_descriptors"][0]["interface_bindings"][0]
        self.assertEqual(descriptor_binding["binding_kind"], "external_input")
        self.assertTrue(descriptor_binding["allowed_external"])
        self.assertEqual(result["repair_context"]["resume_node"], "subsystem_planning")
        self.assertEqual(result["route_decision"]["next_node"], "subsystem_planning")
        self.assertIn("external_input", result["repair_history"][0]["actions"][0])
        self.assertEqual(result["retry_counts_by_scope"]["planning"], 1)
        self.assertEqual(result["subsystem_plan_map"], {})

    def test_assembly_repair_removes_invalid_local_edges(self):
        state = _assembly_state()

        result = RepairAgent()(state)

        subsystem_plan = result["subsystem_plan_map"]["heater_ctrl"]
        self.assertEqual(
            [edge["edge_id"] for edge in subsystem_plan["edges"]],
            ["edge::valid", "edge::ghost_keep"],
        )
        self.assertEqual(subsystem_plan["unresolved_items"][0]["severity"], "warning")
        self.assertEqual(subsystem_plan["unresolved_items"][0]["edge_ids"], ["edge::ghost_remove"])
        self.assertEqual(result["repair_context"]["resume_node"], "global_assembly")
        self.assertEqual(result["route_decision"]["next_node"], "global_assembly")
        self.assertEqual(result["retry_counts_by_scope"]["assembly"], 1)
        self.assertEqual(result["assembled_graph_ir"], {})
        self.assertEqual(result["compiled_artifact"], {})

    def test_compile_repair_prefers_structured_payload_and_clears_compiled_outputs(self):
        state = _compile_state()

        result = RepairAgent()(state)

        self.assertEqual(result["assembled_graph_ir"]["edges"][0]["to_port"], 0)
        self.assertEqual(result["repair_context"]["resume_node"], "coding")
        self.assertEqual(result["route_decision"]["next_node"], "coding")
        self.assertEqual(result["retry_counts_by_scope"]["compile"], 1)
        self.assertEqual(result["compiled_artifact"], {})
        self.assertEqual(result["verification_report"], {})
        self.assertEqual(result["final_output"], {})

    def test_planning_repair_converges_ambiguous_shared_signal_when_filtered_candidates_are_unique(self):
        state = _planning_ambiguous_converge_state()

        result = RepairAgent()(state)

        signal_entry = result["architecture_plan"]["shared_signal_registry"][0]
        self.assertEqual(signal_entry["owner_subsystem_id"], "supply_fan_ctrl")
        self.assertEqual(signal_entry["resolution_status"], "resolved_unique_exporter")
        self.assertEqual(signal_entry["candidate_exporters"], ["supply_fan_ctrl"])
        self.assertEqual(result["route_decision"]["reason"], "repair_patch_applied")
        self.assertEqual(result["repair_context"]["resume_node"], "subsystem_planning")

    def test_planning_repair_rejects_when_ambiguous_shared_signal_remains_unresolved(self):
        state = _planning_ambiguous_unresolved_state()

        result = RepairAgent()(state)

        self.assertEqual(result["route_decision"]["decision"], "reject")
        self.assertEqual(result["route_decision"]["reason"], "ambiguous_shared_signal_unresolved")
        self.assertEqual(result["repair_history"][0]["result"], "rejected")
        self.assertIn("无法收敛唯一 exporter", result["repair_history"][0]["actions"][0])
        self.assertEqual(result["current_step"], "repair_rejected")

    def test_issue_id_filtering_can_trigger_no_repairable_issue(self):
        state = _planning_state()
        state["route_decision"]["issue_ids"] = ["IR-404"]

        result = RepairAgent()(state)

        self.assertEqual(result["route_decision"]["decision"], "reject")
        self.assertEqual(result["route_decision"]["reason"], "no_repairable_issue")
        self.assertEqual(result["repair_history"][0]["result"], "rejected")

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
