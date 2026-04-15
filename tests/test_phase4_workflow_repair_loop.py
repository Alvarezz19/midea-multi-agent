from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import workflow
import workflow_trace


def _shared_signal_owner(state: dict) -> str:
    registry = (state.get("architecture_plan", {}) or {}).get("shared_signal_registry", []) or []
    for entry in registry:
        if entry.get("signal_key") == "supply_fan_available_flag":
            return str(entry.get("owner_subsystem_id", "")).strip()
    return ""


class StubAnalysis:
    def __call__(self, state):
        state["analysis_result"] = {"scenario_analysis": {"summary": "fan heater"}}
        state["requirement_spec"] = {
            "signals": {"inputs": [], "outputs": [], "software_points": [], "alarm_points": []},
            "global_modes": [],
        }
        state["current_step"] = "analysis_completed"
        return state


class StubRetrieval:
    def __call__(self, state):
        state["retrieval_bundle"] = {}
        state["retrieval_context"] = {}
        state["current_step"] = "retrieval_completed"
        return state


class StubArchitecturePlanning:
    def __call__(self, state):
        state["decomposition_result"] = {
            "pages": [],
            "subsystem_descriptors": [
                {"subsystem_id": "supply_fan_ctrl", "imports": [], "exports": ["supply_fan_available_flag"]},
                {"subsystem_id": "heater_ctrl", "imports": ["supply_fan_available_flag"], "exports": ["heater_enable"]},
            ],
            "shared_signal_registry": [
                {
                    "signal_name": "supply_fan_available_flag",
                    "signal_key": "supply_fan_available_flag",
                    "owner_subsystem_id": "",
                    "allowed_external": False,
                    "required_exporter_count": 1,
                    "consumers": ["heater_ctrl"],
                    "source_reason": "projected without owner",
                }
            ],
            "template_needs": [],
            "planning_order": ["supply_fan_ctrl", "heater_ctrl"],
            "warnings": [],
        }
        state["architecture_plan"] = {
            "goal": "fan heater",
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
                    "source_reason": "projected without owner",
                }
            ],
            "global_constraints": [],
            "naming_strategy": {},
            "layout_strategy": {},
            "pattern_bindings": [],
            "warnings": [],
        }
        state["current_step"] = "architecture_planned"
        return state


class StubArchitecturePlanningExternal:
    def __call__(self, state):
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
                        }
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
                    "source_reason": "projected without owner",
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
                    "source_reason": "projected without owner",
                }
            ],
            "global_constraints": [],
            "naming_strategy": {},
            "layout_strategy": {},
            "pattern_bindings": [],
            "warnings": [],
        }
        state["current_step"] = "architecture_planned"
        return state


class StubSubsystemPlanning:
    def __call__(self, state):
        owner = _shared_signal_owner(state)
        if owner == "supply_fan_ctrl":
            state["subsystem_plan_map"] = {
                "supply_fan_ctrl": {"exported_signals": [{"signal_name": "supply_fan_available_flag"}]},
                "heater_ctrl": {"imported_signals": [{"signal_name": "supply_fan_available_flag"}]},
            }
        else:
            state["subsystem_plan_map"] = {
                "supply_fan_ctrl": {"exported_signals": []},
                "heater_ctrl": {"imported_signals": [{"signal_name": "supply_fan_available_flag"}]},
            }
        state["current_step"] = "subsystem_planned"
        return state


class StubSubsystemPlanningExternal:
    def __call__(self, state):
        binding = (
            (state.get("decomposition_result", {}) or {})
            .get("subsystem_descriptors", [{}])[0]
            .get("interface_bindings", [{}])[0]
        )
        if binding.get("binding_kind") == "external_input" and binding.get("allowed_external"):
            state["subsystem_plan_map"] = {
                "supply_fan_ctrl": {
                    "imported_signals": [
                        {
                            "signal_name": "送风机运行状态",
                            "signal_key": "送风机运行状态",
                            "canonical_signal_key": "supply_fan_run_state",
                            "binding_kind": "external_input",
                            "allowed_external": True,
                        }
                    ],
                    "exported_signals": [{"signal_name": "送风机运行标志"}],
                }
            }
        else:
            state["subsystem_plan_map"] = {
                "supply_fan_ctrl": {
                    "imported_signals": [
                        {
                            "signal_name": "送风机运行状态",
                            "signal_key": "送风机运行状态",
                            "canonical_signal_key": "supply_fan_run_state",
                            "binding_kind": "shared_signal",
                            "allowed_external": False,
                        }
                    ],
                    "exported_signals": [{"signal_name": "送风机运行标志"}],
                }
            }
        state["current_step"] = "subsystem_planned"
        return state


class StubGlobalAssembly:
    def __call__(self, state):
        state["assembled_graph_ir"] = {"unresolved_items": []}
        state["execution_plan"] = {"goal": "compat"}
        state["current_step"] = "global_assembly_completed"
        return state


class StubGlobalAssemblyExternal:
    def __call__(self, state):
        imported_signal = (state.get("subsystem_plan_map", {}) or {}).get("supply_fan_ctrl", {}).get("imported_signals", [{}])[0]
        if imported_signal.get("binding_kind") == "external_input" and imported_signal.get("allowed_external"):
            state["assembled_graph_ir"] = {"unresolved_items": []}
        else:
            state["assembled_graph_ir"] = {
                "unresolved_items": [
                    {
                        "type": "synthetic_shared_signal_source",
                        "severity": "error",
                        "scope": "planning",
                        "signal_name": "送风机运行状态",
                        "message": "Shared signal 送风机运行状态 has no real exporter.",
                        "suggested_fix": "Declare it as external input.",
                    }
                ]
            }
        state["execution_plan"] = {"goal": "compat"}
        state["current_step"] = "global_assembly_completed"
        return state


class StubArchitecturePlanningAmbiguous:
    def __call__(self, state):
        state["decomposition_result"] = {
            "pages": [],
            "subsystem_descriptors": [
                {"subsystem_id": "supply_fan_ctrl", "imports": [], "exports": ["supply_fan_available_flag"]},
                {"subsystem_id": "heater_ctrl", "imports": ["supply_fan_available_flag"], "exports": ["heater_enable"]},
                {"subsystem_id": "backup_ctrl", "imports": [], "exports": []},
            ],
            "shared_signal_registry": [
                {
                    "signal_name": "supply_fan_available_flag",
                    "signal_key": "supply_fan_available_flag",
                    "canonical_signal_key": "supply_fan_available",
                    "owner_subsystem_id": "",
                    "allowed_external": False,
                    "required_exporter_count": 1,
                    "candidate_exporters": ["supply_fan_ctrl", "backup_ctrl"],
                    "consumers": ["heater_ctrl"],
                    "source_reason": "projected ambiguous owner",
                }
            ],
            "template_needs": [],
            "planning_order": ["supply_fan_ctrl", "heater_ctrl", "backup_ctrl"],
            "warnings": [],
        }
        state["architecture_plan"] = {
            "goal": "fan heater ambiguous",
            "pages": [],
            "subsystem_slots": [],
            "shared_signal_registry": [
                {
                    "signal_name": "supply_fan_available_flag",
                    "signal_key": "supply_fan_available_flag",
                    "canonical_signal_key": "supply_fan_available",
                    "owner_subsystem_id": "",
                    "allowed_external": False,
                    "required_exporter_count": 1,
                    "candidate_exporters": ["supply_fan_ctrl", "backup_ctrl"],
                    "consumers": ["heater_ctrl"],
                    "source_reason": "projected ambiguous owner",
                }
            ],
            "global_constraints": [],
            "naming_strategy": {},
            "layout_strategy": {},
            "pattern_bindings": [],
            "warnings": [],
        }
        state["current_step"] = "architecture_planned"
        return state


class StubSubsystemPlanningAmbiguousUnique:
    def __call__(self, state):
        owner = _shared_signal_owner(state)
        if owner == "supply_fan_ctrl":
            state["subsystem_plan_map"] = {
                "supply_fan_ctrl": {"exported_signals": [{"signal_name": "supply_fan_available_flag"}]},
                "heater_ctrl": {"imported_signals": [{"signal_name": "supply_fan_available_flag"}]},
                "backup_ctrl": {"exported_signals": []},
            }
        else:
            state["subsystem_plan_map"] = {
                "supply_fan_ctrl": {"exported_signals": [{"signal_name": "supply_fan_available_flag"}]},
                "heater_ctrl": {"imported_signals": [{"signal_name": "supply_fan_available_flag"}]},
                "backup_ctrl": {"exported_signals": []},
            }
        state["current_step"] = "subsystem_planned"
        return state


class StubSubsystemPlanningAmbiguousConflict:
    def __call__(self, state):
        state["subsystem_plan_map"] = {
            "supply_fan_ctrl": {"exported_signals": [{"signal_name": "supply_fan_available_flag"}]},
            "heater_ctrl": {"imported_signals": [{"signal_name": "supply_fan_available_flag"}]},
            "backup_ctrl": {"exported_signals": [{"signal_name": "supply_fan_available_flag"}]},
        }
        state["current_step"] = "subsystem_planned"
        return state


class StubVerifierAmbiguousSuccessAfterRepair:
    def __call__(self, state):
        owner = _shared_signal_owner(state)
        if owner == "supply_fan_ctrl":
            report = {
                "status": "passed",
                "repair_scope": "none",
                "issue_summary": "结构校验通过。",
                "issues": [],
                "warnings": [],
                "metrics": {},
            }
        else:
            report = {
                "status": "retryable_error",
                "repair_scope": "planning",
                "issue_summary": "发现 1 个结构错误。",
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
                            "candidate_exporters": ["supply_fan_ctrl", "backup_ctrl"],
                            "consumer_subsystem_ids": ["heater_ctrl"],
                            "resolution_status": "ambiguous",
                        },
                    }
                ],
                "warnings": [],
                "metrics": {},
            }
        state["verification_report"] = report
        state["final_output"] = {"verification_report": report}
        state["current_step"] = "verification_completed"
        return state


class StubVerifierAmbiguousReject:
    def __call__(self, state):
        report = {
            "status": "retryable_error",
            "repair_scope": "planning",
            "issue_summary": "发现 1 个结构错误。",
            "issues": [
                {
                    "issue_id": "IR-AMB-002",
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
            ],
            "warnings": [],
            "metrics": {},
        }
        state["verification_report"] = report
        state["final_output"] = {"verification_report": report}
        state["current_step"] = "verification_completed"
        return state


class StubCoding:
    def __call__(self, state):
        state["compiled_artifact"] = {"json_text": "[]", "flow_objects": [], "compile_report": {"warnings": []}}
        state["generated_code"] = "[]"
        state["current_step"] = "coding_completed"
        return state


class StubVerifierSuccessAfterRepair:
    def __call__(self, state):
        owner = _shared_signal_owner(state)
        if owner == "supply_fan_ctrl":
            report = {
                "status": "passed",
                "repair_scope": "none",
                "issue_summary": "结构校验通过。",
                "issues": [],
                "warnings": [],
                "metrics": {},
            }
        else:
            report = {
                "status": "retryable_error",
                "repair_scope": "planning",
                "issue_summary": "发现 1 个结构错误。",
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
        state["verification_report"] = report
        state["final_output"] = {"verification_report": report}
        state["current_step"] = "verification_completed"
        return state


class StubVerifierReject:
    def __call__(self, state):
        report = {
            "status": "retryable_error",
            "repair_scope": "planning",
            "issue_summary": "发现 1 个结构错误。",
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
        state["verification_report"] = report
        state["final_output"] = {"verification_report": report}
        state["current_step"] = "verification_completed"
        return state


class StubVerifierExternalAfterRepair:
    def __call__(self, state):
        imported_signal = (state.get("subsystem_plan_map", {}) or {}).get("supply_fan_ctrl", {}).get("imported_signals", [{}])[0]
        if imported_signal.get("binding_kind") == "external_input" and imported_signal.get("allowed_external"):
            report = {
                "status": "passed",
                "repair_scope": "none",
                "issue_summary": "结构校验通过。",
                "issues": [],
                "warnings": [],
                "metrics": {},
            }
        else:
            report = {
                "status": "retryable_error",
                "repair_scope": "planning",
                "issue_summary": "发现 1 个结构错误。",
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
        state["verification_report"] = report
        state["final_output"] = {"verification_report": report}
        state["current_step"] = "verification_completed"
        return state


class Phase4WorkflowRepairLoopTests(unittest.TestCase):
    def test_workflow_repairs_planning_issue_and_reaches_passed(self):
        with patch.object(workflow, "AnalysisAgent", StubAnalysis), \
             patch.object(workflow, "RetrievalAgent", StubRetrieval), \
             patch.object(workflow, "ArchitecturePlanner", StubArchitecturePlanning), \
             patch.object(workflow, "SubsystemPlanner", StubSubsystemPlanning), \
             patch.object(workflow, "GlobalAssembler", StubGlobalAssembly), \
             patch.object(workflow, "CodingAgent", StubCoding), \
             patch.object(workflow, "VerifierAgent", StubVerifierSuccessAfterRepair):
            result = workflow.run_workflow("fan heater")

        self.assertEqual(result["verification_report"]["status"], "passed")
        self.assertEqual(result["route_decision"]["decision"], "accept")
        self.assertEqual(result["retry_counts_by_scope"]["planning"], 1)
        self.assertEqual(result["repair_history"][0]["scope"], "planning")
        self.assertEqual(_shared_signal_owner(result), "supply_fan_ctrl")
        self.assertEqual(result["current_step"], "verification_completed")

    def test_workflow_rejects_unsupported_issue_after_router(self):
        with patch.object(workflow, "AnalysisAgent", StubAnalysis), \
             patch.object(workflow, "RetrievalAgent", StubRetrieval), \
             patch.object(workflow, "ArchitecturePlanner", StubArchitecturePlanning), \
             patch.object(workflow, "SubsystemPlanner", StubSubsystemPlanning), \
             patch.object(workflow, "GlobalAssembler", StubGlobalAssembly), \
             patch.object(workflow, "CodingAgent", StubCoding), \
             patch.object(workflow, "VerifierAgent", StubVerifierReject):
            result = workflow.run_workflow("fan heater")

        self.assertEqual(result["verification_report"]["status"], "retryable_error")
        self.assertEqual(result["route_decision"]["decision"], "reject")
        self.assertEqual(result["route_decision"]["reason"], "unsupported_repair_issue")
        self.assertEqual(result["repair_history"][0]["result"], "rejected")
        self.assertEqual(result["retry_counts_by_scope"]["planning"], 1)
        self.assertEqual(result["current_step"], "repair_rejected")

    def test_workflow_reclassifies_external_planning_issue_and_reaches_passed(self):
        with patch.object(workflow, "AnalysisAgent", StubAnalysis), \
             patch.object(workflow, "RetrievalAgent", StubRetrieval), \
             patch.object(workflow, "ArchitecturePlanner", StubArchitecturePlanningExternal), \
             patch.object(workflow, "SubsystemPlanner", StubSubsystemPlanningExternal), \
             patch.object(workflow, "GlobalAssembler", StubGlobalAssemblyExternal), \
             patch.object(workflow, "CodingAgent", StubCoding), \
             patch.object(workflow, "VerifierAgent", StubVerifierExternalAfterRepair):
            result = workflow.run_workflow("fan external")

        self.assertEqual(result["verification_report"]["status"], "passed")
        self.assertEqual(result["route_decision"]["decision"], "accept")
        self.assertEqual(result["retry_counts_by_scope"]["planning"], 1)
        self.assertIn("external_input", result["repair_history"][0]["actions"][0])
        binding = result["decomposition_result"]["subsystem_descriptors"][0]["interface_bindings"][0]
        self.assertEqual(binding["binding_kind"], "external_input")
        self.assertTrue(binding["allowed_external"])

    def test_workflow_repairs_ambiguous_shared_signal_when_candidates_converge(self):
        with patch.object(workflow, "AnalysisAgent", StubAnalysis), \
             patch.object(workflow, "RetrievalAgent", StubRetrieval), \
             patch.object(workflow, "ArchitecturePlanner", StubArchitecturePlanningAmbiguous), \
             patch.object(workflow, "SubsystemPlanner", StubSubsystemPlanningAmbiguousUnique), \
             patch.object(workflow, "GlobalAssembler", StubGlobalAssembly), \
             patch.object(workflow, "CodingAgent", StubCoding), \
             patch.object(workflow, "VerifierAgent", StubVerifierAmbiguousSuccessAfterRepair):
            result = workflow.run_workflow("fan heater ambiguous unique")

        self.assertEqual(result["verification_report"]["status"], "passed")
        self.assertEqual(result["route_decision"]["decision"], "accept")
        self.assertEqual(result["retry_counts_by_scope"]["planning"], 1)
        self.assertEqual(_shared_signal_owner(result), "supply_fan_ctrl")

    def test_workflow_rejects_ambiguous_shared_signal_when_candidates_remain_multiple(self):
        with patch.object(workflow, "AnalysisAgent", StubAnalysis), \
             patch.object(workflow, "RetrievalAgent", StubRetrieval), \
             patch.object(workflow, "ArchitecturePlanner", StubArchitecturePlanningAmbiguous), \
             patch.object(workflow, "SubsystemPlanner", StubSubsystemPlanningAmbiguousConflict), \
             patch.object(workflow, "GlobalAssembler", StubGlobalAssembly), \
             patch.object(workflow, "CodingAgent", StubCoding), \
             patch.object(workflow, "VerifierAgent", StubVerifierAmbiguousReject):
            result = workflow.run_workflow("fan heater ambiguous reject")

        self.assertEqual(result["verification_report"]["status"], "retryable_error")
        self.assertEqual(result["route_decision"]["decision"], "reject")
        self.assertEqual(result["route_decision"]["reason"], "ambiguous_shared_signal_unresolved")
        self.assertEqual(result["repair_history"][0]["result"], "rejected")
        self.assertEqual(result["retry_counts_by_scope"]["planning"], 1)
        self.assertEqual(result["current_step"], "repair_rejected")

    def test_workflow_trace_records_repair_router_and_repair_agent(self):
        captured_records: dict[str, list[dict]] = {}

        def _capture_trace(user_query: str, node_io_records: list[dict], final_state: dict, total_elapsed_seconds: float) -> dict:
            del user_query, final_state, total_elapsed_seconds
            captured_records["nodes"] = list(node_io_records)
            return {"trace_dir": "mock-trace"}

        with patch.object(workflow_trace, "AnalysisAgent", StubAnalysis), \
             patch.object(workflow_trace, "RetrievalAgent", StubRetrieval), \
             patch.object(workflow_trace, "ArchitecturePlanner", StubArchitecturePlanning), \
             patch.object(workflow_trace, "SubsystemPlanner", StubSubsystemPlanning), \
             patch.object(workflow_trace, "GlobalAssembler", StubGlobalAssembly), \
             patch.object(workflow_trace, "CodingAgent", StubCoding), \
             patch.object(workflow_trace, "VerifierAgent", StubVerifierSuccessAfterRepair), \
             patch.object(workflow_trace, "_save_workflow_trace", side_effect=_capture_trace):
            result = workflow_trace.run_workflow("fan heater")

        node_names = [record["node_name"] for record in captured_records["nodes"]]
        self.assertIn("repair_router", node_names)
        self.assertIn("repair_agent", node_names)
        self.assertGreaterEqual(node_names.count("subsystem_planning"), 2)
        self.assertEqual(result["final_output"]["workflow_trace"]["trace_dir"], "mock-trace")


if __name__ == "__main__":
    unittest.main()
