from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
from agents.coding_agent import CodingAgent
from agents.verifier_agent import VerifierAgent


def make_bundle() -> dict:
    return {
        "atomic_modules": [
            {
                "module_type": "constInput",
                "name": "Constant Input",
                "category": "logic/basic",
                "description": "Provide a constant numeric value.",
                "parameters_schema": {
                    "name": {"type": "string"},
                    "fixedValue": {"type": "number"},
                },
                "ports_definition": {"inputs": [], "outputs": [{"index": 0, "label": "out"}]},
                "template_json": {"type": "constInput", "inputs": 0, "outputs": 1},
            }
        ],
        "subflow_templates": [],
        "system_patterns": [],
        "style_guides": [],
        "metadata": {},
    }


def make_requirement_spec() -> dict:
    return {
        "schema_version": "3.0",
        "system_type": "AHU",
        "scenario_summary": "送风机控制",
        "subsystems": [
            {
                "subsystem_id": "supply_fan_ctrl",
                "subsystem_type": "supply_fan_control",
                "goal": "送风机控制",
                "imports": ["schedule_enable"],
                "exports": ["supply_fan_available_flag"],
            }
        ],
        "signals": {
            "inputs": ["schedule_enable"],
            "outputs": ["supply_fan_available_flag"],
            "software_points": ["schedule_enable"],
            "alarm_points": [],
        },
        "required_pages": ["控制"],
        "global_modes": ["schedule_enable"],
        "warnings": [],
    }


def make_architecture_plan() -> dict:
    return {
        "goal": "送风机控制",
        "pages": [{"page_id": "page_control", "label": "控制", "kind": "control", "order": 0}],
        "subsystem_slots": [
            {
                "subsystem_id": "supply_fan_ctrl",
                "page_id": "page_control",
                "preferred_implementation": "atomic_assembly",
                "preferred_template_ids": [],
                "fallback_mode": "atomic_assembly",
            }
        ],
        "shared_signal_registry": [
            {
                "signal_name": "schedule_enable",
                "signal_key": "schedule_enable",
                "owner_subsystem_id": "",
                "allowed_external": True,
                "required_exporter_count": 0,
                "consumers": ["supply_fan_ctrl"],
                "source_reason": "global mode",
            }
        ],
        "global_constraints": [],
        "naming_strategy": {},
        "layout_strategy": {},
        "pattern_bindings": [],
        "warnings": [],
    }


def make_subsystem_plan_map() -> dict:
    return {
        "supply_fan_ctrl": {
            "subsystem_id": "supply_fan_ctrl",
            "page_id": "page_control",
            "implementation_mode": "atomic_assembly",
            "template_binding": {"template_id": "", "degraded": True},
            "node_instances": [
                {
                    "logic_id": "fan_main",
                    "module_type": "constInput",
                    "page_id": "page_control",
                    "template_id": None,
                    "parameters": {"name": "Supply Fan Enable", "fixedValue": 1},
                    "input_count": 0,
                    "output_count": 1,
                    "position": {"x": 100, "y": 100},
                    "reasoning": "native verifier test",
                }
            ],
            "edges": [],
            "imported_signals": [],
            "exported_signals": [
                {
                    "signal_name": "supply_fan_available_flag",
                    "node_logic_id": "fan_main",
                    "port_index": 0,
                    "page_id": "page_control",
                }
            ],
            "constraints": [],
            "unresolved_items": [],
            "reasoning": "native verifier test",
        }
    }


def make_graph_ir() -> dict:
    return {
        "graph_ir_version": "2.0",
        "goal": "送风机控制",
        "pages": [{"page_id": "page_control", "label": "控制", "kind": "control", "order": 0}],
        "subflow_definitions": [],
        "node_instances": [
            {
                "instance_id": "node::supply_fan_ctrl::fan_main",
                "logic_id": "fan_main",
                "module_type": "constInput",
                "page_id": "page_control",
                "subflow_id": None,
                "template_id": None,
                "parameters": {"name": "Supply Fan Enable", "fixedValue": 1},
                "position": {"x": 100, "y": 100},
                "input_count": 0,
                "output_count": 1,
                "reasoning": "native verifier test",
            }
        ],
        "edges": [],
        "signal_registry": [],
        "layout_hints": {},
        "unresolved_items": [],
    }


class Phase3VerifierNativeContractTests(unittest.TestCase):
    def test_verifier_accepts_native_phase3_contract_without_source_execution_plan(self):
        graph_ir = make_graph_ir()

        with patch.object(config, "DEBUG", False):
            artifact = CodingAgent().compile_graph(graph_ir, make_bundle())
            report = VerifierAgent().verify(
                graph_ir,
                artifact,
                requirement_spec=make_requirement_spec(),
                architecture_plan=make_architecture_plan(),
                subsystem_plan_map=make_subsystem_plan_map(),
            )

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["repair_scope"], "none")

    def test_verifier_fails_cleanly_when_native_subsystem_plan_map_is_missing(self):
        graph_ir = {
            "graph_ir_version": "2.0",
            "goal": "送风机控制",
            "pages": [{"page_id": "page_control", "label": "控制", "kind": "control", "order": 0}],
            "subflow_definitions": [],
            "node_instances": [],
            "edges": [],
            "signal_registry": [],
            "layout_hints": {},
            "unresolved_items": [],
        }
        artifact = {
            "json_text": "[]",
            "flow_objects": [],
            "id_map": {},
            "layout_map": {},
            "compile_report": {"node_count": 0, "subflow_count": 0, "page_count": 0, "warnings": []},
        }

        with patch.object(config, "DEBUG", False):
            report = VerifierAgent().verify(
                graph_ir,
                artifact,
                requirement_spec=make_requirement_spec(),
                architecture_plan=make_architecture_plan(),
                subsystem_plan_map={},
            )

        self.assertEqual(report["status"], "retryable_error")
        self.assertEqual(report["repair_scope"], "planning")
        self.assertTrue(
            any(issue["rule_id"] == "plan.subsystem_plan_map.must_not_be_empty" for issue in report["issues"])
        )

    def test_verifier_keeps_planning_scope_for_native_unresolved_items(self):
        graph_ir = make_graph_ir()
        graph_ir["unresolved_items"] = [
            {
                "type": "synthetic_shared_signal_source",
                "severity": "error",
                "scope": "planning",
                "signal_name": "schedule_enable",
                "message": "Shared signal schedule_enable has no real exporter.",
                "suggested_fix": "Declare it as external input or export it from a real subsystem.",
            }
        ]

        with patch.object(config, "DEBUG", False):
            artifact = CodingAgent().compile_graph(graph_ir, make_bundle())
            report = VerifierAgent().verify(
                graph_ir,
                artifact,
                requirement_spec=make_requirement_spec(),
                architecture_plan=make_architecture_plan(),
                subsystem_plan_map=make_subsystem_plan_map(),
            )

        self.assertEqual(report["status"], "retryable_error")
        self.assertEqual(report["repair_scope"], "planning")
        issue = next(
            issue for issue in report["issues"]
            if issue["rule_id"] == "ir.unresolved.synthetic_shared_signal_source"
        )
        self.assertEqual(issue["repair_payload"]["signal_name"], "schedule_enable")
        self.assertEqual(issue["repair_payload"]["binding_kind"], "external_input")
        self.assertTrue(issue["repair_payload"]["allowed_external"])
        self.assertEqual(issue["repair_payload"]["resolution_status"], "externalized")

    def test_verifier_reports_native_planning_unresolved_items_without_compat_projection(self):
        graph_ir = make_graph_ir()
        graph_ir["unresolved_items"] = [
            {
                "type": "synthetic_shared_signal_source",
                "severity": "error",
                "scope": "planning",
                "signal_name": "schedule_enable",
                "message": "Shared signal schedule_enable has no real exporter.",
                "suggested_fix": "Declare it as external input or export it from a real subsystem.",
            }
        ]

        with patch.object(config, "DEBUG", False):
            artifact = CodingAgent().compile_graph(graph_ir, make_bundle())
            report = VerifierAgent().verify(
                graph_ir,
                artifact,
                requirement_spec=make_requirement_spec(),
                architecture_plan=make_architecture_plan(),
                subsystem_plan_map=make_subsystem_plan_map(),
            )

        self.assertEqual(report["status"], "retryable_error")
        self.assertEqual(report["repair_scope"], "planning")
        self.assertTrue(
            any(issue["rule_id"] == "plan.unresolved_items.must_be_resolved" for issue in report["issues"])
        )

    def test_verifier_projects_structured_payload_for_assembly_unresolved_item(self):
        graph_ir = {
            "graph_ir_version": "2.0",
            "goal": "assembly repair payload",
            "pages": [{"page_id": "page_control", "label": "控制", "kind": "control", "order": 0}],
            "subflow_definitions": [],
            "node_instances": [
                {
                    "instance_id": "node::heater",
                    "logic_id": "heater_main",
                    "module_type": "constInput",
                    "page_id": "page_control",
                    "subflow_id": None,
                    "template_id": None,
                    "parameters": {"name": "heater", "fixedValue": 1},
                    "position": {"x": 0, "y": 0},
                    "input_count": 1,
                    "output_count": 1,
                    "reasoning": "assembly payload",
                }
            ],
            "edges": [],
            "signal_registry": [],
            "layout_hints": {},
            "unresolved_items": [
                {
                    "type": "missing_local_edge_endpoint",
                    "severity": "error",
                    "scope": "assembly",
                    "subsystem_id": "heater_ctrl",
                    "message": "Local edge references missing nodes.",
                    "edge_locator": {
                        "subsystem_id": "heater_ctrl",
                        "edge_ids": ["edge::ghost"],
                        "from_node": "ghost_source",
                        "to_node": "heater_main",
                    },
                    "reason": "missing_local_edge_endpoint",
                }
            ],
        }
        artifact = {
            "json_text": "[]",
            "flow_objects": [
                {"id": "tab1", "type": "tab", "label": "控制"},
                {"id": "heater1", "type": "constInput", "z": "tab1", "wires": [[]], "inputs": 1, "outputs": 1},
            ],
            "id_map": {"node::heater": "heater1"},
            "layout_map": {},
            "compile_report": {"node_count": 1, "subflow_count": 0, "page_count": 1, "warnings": []},
        }

        with patch.object(config, "DEBUG", False):
            report = VerifierAgent().verify(
                graph_ir,
                artifact,
                requirement_spec=make_requirement_spec(),
                architecture_plan=make_architecture_plan(),
                subsystem_plan_map=make_subsystem_plan_map(),
            )

        issue = next(
            issue for issue in report["issues"]
            if issue["rule_id"] == "ir.unresolved.missing_local_edge_endpoint"
        )
        self.assertEqual(issue["repair_payload"]["subsystem_id"], "heater_ctrl")
        self.assertEqual(issue["repair_payload"]["edge_ids"], ["edge::ghost"])
        self.assertEqual(issue["repair_payload"]["from_node"], "ghost_source")
        self.assertEqual(issue["repair_payload"]["to_node"], "heater_main")
        self.assertEqual(issue["repair_payload"]["reason"], "missing_local_edge_endpoint")

    def test_verifier_emits_structured_payload_for_compile_port_range_issue(self):
        graph_ir = {
            "graph_ir_version": "2.0",
            "goal": "compile repair payload",
            "pages": [{"page_id": "page_control", "label": "控制", "kind": "control", "order": 0}],
            "subflow_definitions": [],
            "node_instances": [
                {
                    "instance_id": "node::src",
                    "logic_id": "src",
                    "module_type": "constInput",
                    "page_id": "page_control",
                    "subflow_id": None,
                    "template_id": None,
                    "parameters": {"name": "src", "fixedValue": 1},
                    "position": {"x": 0, "y": 0},
                    "input_count": 0,
                    "output_count": 1,
                    "reasoning": "src",
                },
                {
                    "instance_id": "node::dst",
                    "logic_id": "dst",
                    "module_type": "constInput",
                    "page_id": "page_control",
                    "subflow_id": None,
                    "template_id": None,
                    "parameters": {"name": "dst", "fixedValue": 0},
                    "position": {"x": 120, "y": 0},
                    "input_count": 1,
                    "output_count": 1,
                    "reasoning": "dst",
                },
            ],
            "edges": [],
            "signal_registry": [],
            "layout_hints": {},
            "unresolved_items": [],
        }
        artifact = {
            "json_text": "[]",
            "flow_objects": [
                {"id": "src1", "type": "constInput", "wires": [[{"id": "dst1", "port": 2}]], "inputs": 0, "outputs": 1},
                {"id": "dst1", "type": "constInput", "wires": [[]], "inputs": 1, "outputs": 1},
            ],
            "id_map": {"node::src": "src1", "node::dst": "dst1"},
            "layout_map": {},
            "compile_report": {"node_count": 2, "subflow_count": 0, "page_count": 1, "warnings": []},
        }

        with patch.object(config, "DEBUG", False):
            report = VerifierAgent().verify(
                graph_ir,
                artifact,
                requirement_spec=make_requirement_spec(),
                architecture_plan=make_architecture_plan(),
                subsystem_plan_map=make_subsystem_plan_map(),
            )

        issue = next(
            issue for issue in report["issues"]
            if issue["rule_id"] == "compile.wire.port.range"
        )
        self.assertEqual(issue["repair_payload"]["source_real_id"], "src1")
        self.assertEqual(issue["repair_payload"]["target_real_id"], "dst1")
        self.assertEqual(issue["repair_payload"]["invalid_target_port"], 2)
        self.assertEqual(issue["repair_payload"]["target_input_count"], 1)


if __name__ == "__main__":
    unittest.main()
