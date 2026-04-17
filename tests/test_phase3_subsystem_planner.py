from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
from agents.subsystem_planner import SubsystemPlanner


def make_bundle(include_template: bool = True) -> dict:
    bundle = {
        "atomic_modules": [
            {
                "module_type": "constInput",
                "name": "Constant Input",
                "category": "logic/basic",
                "description": "Provide a constant numeric value.",
                "parameters_schema": {"fixedValue": {"type": "number"}},
                "ports_definition": {"inputs": [], "outputs": [{"index": 0, "label": "out"}]},
                "template_json": {"type": "constInput", "inputs": 0, "outputs": 1},
            },
            {
                "module_type": "add",
                "name": "Add",
                "category": "math/basic",
                "description": "Add numeric signals.",
                "parameters_schema": {"inputCount": {"type": "integer"}, "name": {"type": "string"}},
                "ports_definition": {
                    "inputs": [{"index": 0, "label": "in0"}, {"index": 1, "label": "in1"}],
                    "outputs": [{"index": 0, "label": "out"}],
                },
                "template_json": {"type": "add", "inputs": "{{inputCount}}", "outputs": 1},
            },
        ],
        "subflow_templates": [],
        "system_patterns": [],
        "style_guides": [],
        "metadata": {},
    }
    if include_template:
        bundle["subflow_templates"] = [
            {
                "module_type": "fan_template",
                "asset_type": "subflow_template",
                "template_id": "fan_template",
                "definition_id": "fan_template",
                "template_name": "送风机标准控制",
                "template_role": "supply_fan_control",
                "name": "送风机标准控制",
                "category": "AHU/subflow_templates/fan_control",
                "description": "Reusable fan control subflow.",
                "parameters_schema": {},
                "ports_definition": {
                    "inputs": [
                        {"index": 0, "label": "schedule_enable"},
                        {"index": 1, "label": "fan_fault_reset"},
                    ],
                    "outputs": [
                        {"index": 0, "label": "supply_fan_available_flag"},
                    ],
                },
                "template_json": {
                    "type": "subflow",
                    "id": "fan_template",
                    "name": "送风机标准控制",
                    "in": [
                        {"x": 60, "y": 80, "name": "schedule_enable", "wires": []},
                        {"x": 60, "y": 140, "name": "fan_fault_reset", "wires": []},
                    ],
                    "out": [{"x": 380, "y": 110, "name": "supply_fan_available_flag", "wires": []}],
                    "inputs": 2,
                    "outputs": 1,
                },
                "compile_hints": {"input_count": 2, "output_count": 1},
            }
        ]
    return bundle


def make_decomposition_and_architecture(prefer_template: bool = True) -> tuple[dict, dict]:
    decomposition_result = {
        "pages": [{"page_id": "page_control", "label": "控制", "kind": "control", "order": 0}],
        "subsystem_descriptors": [
            {
                "subsystem_id": "supply_fan_ctrl",
                "subsystem_type": "supply_fan_control",
                "page_id": "page_control",
                "goal": "送风机控制",
                "implementation_preference": "reuse_template" if prefer_template else "atomic_assembly",
                "interface_bindings": [
                    {
                        "signal_name": "schedule_enable",
                        "signal_key": "schedule_enable",
                        "canonical_signal_key": "schedule_enable",
                        "direction": "input",
                        "binding_kind": "external_input",
                        "allowed_external": True,
                        "owner_subsystem_id": "",
                        "port_index": 0,
                    },
                    {
                        "signal_name": "fan_fault_reset",
                        "signal_key": "fan_fault_reset",
                        "canonical_signal_key": "fan_fault_reset",
                        "direction": "input",
                        "binding_kind": "external_command",
                        "allowed_external": True,
                        "owner_subsystem_id": "",
                        "port_index": 1,
                    },
                    {
                        "signal_name": "supply_fan_available_flag",
                        "signal_key": "supply_fan_available_flag",
                        "canonical_signal_key": "supply_fan_available_flag",
                        "direction": "output",
                        "binding_kind": "shared_signal",
                        "allowed_external": False,
                        "owner_subsystem_id": "supply_fan_ctrl",
                        "port_index": 0,
                    },
                ],
                "imports": ["schedule_enable", "fan_fault_reset"],
                "exports": ["supply_fan_available_flag"],
                "priority": 1,
                "reasoning": "phase3 test",
            }
        ],
        "shared_signal_registry": [],
        "template_needs": [],
        "planning_order": ["supply_fan_ctrl"],
        "warnings": [],
    }
    architecture_plan = {
        "goal": "送风机控制",
        "pages": [{"page_id": "page_control", "label": "控制", "kind": "control", "order": 0}],
        "subsystem_slots": [
            {
                "subsystem_id": "supply_fan_ctrl",
                "page_id": "page_control",
                "preferred_implementation": "reuse_template" if prefer_template else "atomic_assembly",
                "preferred_template_ids": ["fan_template"] if prefer_template else [],
                "score_breakdown": [{"template_id": "fan_template", "score": 20}] if prefer_template else [],
                "selection_reason": "Selected reusable template fan_template." if prefer_template else "No qualified reusable template matched current subsystem context.",
                "degrade_reason": "" if prefer_template else "No qualified reusable template matched current subsystem context; fallback to atomic_assembly.",
                "fallback_mode": "atomic_assembly",
                "priority": 1,
                "reasoning": "phase3 test slot",
            }
        ],
        "shared_signal_registry": list(decomposition_result["shared_signal_registry"]),
        "global_constraints": [],
        "naming_strategy": {},
        "layout_strategy": {},
        "pattern_bindings": [],
        "warnings": [],
    }
    return decomposition_result, architecture_plan


def make_multi_subsystem_inputs() -> tuple[dict, dict]:
    decomposition_result = {
        "pages": [{"page_id": "page_control", "label": "控制", "kind": "control", "order": 0}],
        "subsystem_descriptors": [
            {
                "subsystem_id": "supply_fan_ctrl",
                "subsystem_type": "supply_fan_control",
                "page_id": "page_control",
                "goal": "送风机控制",
                "implementation_preference": "reuse_template",
                "interface_bindings": [
                    {
                        "signal_name": "schedule_enable",
                        "signal_key": "schedule_enable",
                        "canonical_signal_key": "schedule_enable",
                        "direction": "input",
                        "binding_kind": "external_input",
                        "allowed_external": True,
                        "owner_subsystem_id": "",
                        "port_index": 0,
                    },
                    {
                        "signal_name": "fan_fault_reset",
                        "signal_key": "fan_fault_reset",
                        "canonical_signal_key": "fan_fault_reset",
                        "direction": "input",
                        "binding_kind": "external_command",
                        "allowed_external": True,
                        "owner_subsystem_id": "",
                        "port_index": 1,
                    },
                    {
                        "signal_name": "supply_fan_available_flag",
                        "signal_key": "supply_fan_available_flag",
                        "canonical_signal_key": "supply_fan_available_flag",
                        "direction": "output",
                        "binding_kind": "shared_signal",
                        "allowed_external": False,
                        "owner_subsystem_id": "supply_fan_ctrl",
                        "port_index": 0,
                    },
                ],
                "imports": ["schedule_enable", "fan_fault_reset"],
                "exports": ["supply_fan_available_flag"],
                "priority": 1,
                "reasoning": "fan",
            },
            {
                "subsystem_id": "heater_ctrl",
                "subsystem_type": "heater_control",
                "page_id": "page_control",
                "goal": "电加热控制",
                "implementation_preference": "atomic_assembly",
                "interface_bindings": [
                    {
                        "signal_name": "schedule_enable",
                        "signal_key": "schedule_enable",
                        "canonical_signal_key": "schedule_enable",
                        "direction": "input",
                        "binding_kind": "external_input",
                        "allowed_external": True,
                        "owner_subsystem_id": "",
                        "port_index": 0,
                    },
                    {
                        "signal_name": "supply_fan_available_flag",
                        "signal_key": "supply_fan_available_flag",
                        "canonical_signal_key": "supply_fan_available_flag",
                        "direction": "input",
                        "binding_kind": "shared_signal",
                        "allowed_external": False,
                        "owner_subsystem_id": "supply_fan_ctrl",
                        "port_index": 1,
                    },
                    {
                        "signal_name": "heater_enable",
                        "signal_key": "heater_enable",
                        "canonical_signal_key": "heater_enable",
                        "direction": "output",
                        "binding_kind": "subsystem_output",
                        "allowed_external": False,
                        "owner_subsystem_id": "",
                        "port_index": 0,
                    },
                ],
                "imports": ["schedule_enable", "supply_fan_available_flag"],
                "exports": ["heater_enable"],
                "priority": 2,
                "reasoning": "heater",
            },
        ],
        "shared_signal_registry": [
            {
                "signal_name": "supply_fan_available_flag",
                "signal_key": "supply_fan_available_flag",
                "canonical_signal_key": "supply_fan_available_flag",
                "owner_subsystem_id": "supply_fan_ctrl",
                "allowed_external": False,
                "required_exporter_count": 1,
                "consumers": ["heater_ctrl"],
                "candidate_exporters": ["supply_fan_ctrl"],
                "resolution_status": "resolved",
                "resolution_evidence": ["consumers=heater_ctrl", "exporters=supply_fan_ctrl", "owner=supply_fan_ctrl"],
                "source_reason": "fan export",
            },
        ],
        "template_needs": [],
        "planning_order": ["supply_fan_ctrl", "heater_ctrl"],
        "warnings": [],
    }
    architecture_plan = {
        "goal": "送风机与电加热联动",
        "pages": [{"page_id": "page_control", "label": "控制", "kind": "control", "order": 0}],
        "subsystem_slots": [
            {
                "subsystem_id": "supply_fan_ctrl",
                "page_id": "page_control",
                "preferred_implementation": "reuse_template",
                "preferred_template_ids": ["fan_template"],
                "score_breakdown": [{"template_id": "fan_template", "score": 24}],
                "selection_reason": "Selected reusable template fan_template.",
                "degrade_reason": "",
                "fallback_mode": "atomic_assembly",
                "priority": 1,
                "reasoning": "fan",
            },
            {
                "subsystem_id": "heater_ctrl",
                "page_id": "page_control",
                "preferred_implementation": "atomic_assembly",
                "preferred_template_ids": [],
                "score_breakdown": [],
                "selection_reason": "No qualified reusable template matched current subsystem context.",
                "degrade_reason": "No qualified reusable template matched current subsystem context; fallback to atomic_assembly.",
                "fallback_mode": "atomic_assembly",
                "priority": 2,
                "reasoning": "heater",
            },
        ],
        "shared_signal_registry": list(decomposition_result["shared_signal_registry"]),
        "global_constraints": [],
        "naming_strategy": {},
        "layout_strategy": {},
        "pattern_bindings": [],
        "warnings": [],
    }
    return decomposition_result, architecture_plan


class Phase3SubsystemPlannerTests(unittest.TestCase):
    def test_subsystem_planner_prefers_template_reuse(self):
        decomposition_result, architecture_plan = make_decomposition_and_architecture(prefer_template=True)

        with patch.object(config, "DEBUG", False):
            planner = SubsystemPlanner()
            subsystem_plan_map = planner.plan({}, decomposition_result, architecture_plan, make_bundle(include_template=True))

        plan = subsystem_plan_map["supply_fan_ctrl"]
        self.assertEqual(plan["implementation_mode"], "reuse_template")
        self.assertEqual(plan["template_binding"]["template_id"], "fan_template")
        self.assertEqual(plan["node_instances"][0]["template_id"], "fan_template")
        self.assertEqual(len(plan["imported_signals"]), 2)
        self.assertEqual(plan["imported_signals"][0]["binding_kind"], "external_input")
        self.assertTrue(plan["imported_signals"][0]["allowed_external"])
        self.assertEqual(plan["imported_signals"][1]["binding_kind"], "external_command")
        self.assertEqual(plan["exported_signals"][0]["signal_name"], "supply_fan_available_flag")
        self.assertEqual(plan["exported_signals"][0]["binding_kind"], "shared_signal")
        self.assertTrue(plan["template_interface_bindings"])
        self.assertTrue(plan["selection_reason"])
        self.assertEqual(plan["degrade_reason"], "")
        self.assertTrue(plan["template_binding"]["score_breakdown"])

    def test_subsystem_planner_falls_back_to_atomic_assembly(self):
        decomposition_result, architecture_plan = make_decomposition_and_architecture(prefer_template=False)

        with patch.object(config, "DEBUG", False):
            planner = SubsystemPlanner()
            subsystem_plan_map = planner.plan({}, decomposition_result, architecture_plan, make_bundle(include_template=False))

        plan = subsystem_plan_map["supply_fan_ctrl"]
        self.assertEqual(plan["implementation_mode"], "atomic_assembly")
        self.assertGreaterEqual(len(plan["node_instances"]), 2)
        self.assertGreaterEqual(len(plan["edges"]), 1)
        self.assertEqual(plan["node_instances"][0]["module_type"], "add")
        self.assertEqual(plan["imported_signals"][0]["signal_name"], "schedule_enable")
        self.assertEqual(plan["imported_signals"][0]["binding_kind"], "external_input")
        self.assertEqual(plan["exported_signals"][0]["signal_name"], "supply_fan_available_flag")
        self.assertTrue(plan["template_binding"]["degraded"])
        self.assertTrue(plan["selection_reason"])
        self.assertTrue(plan["degrade_reason"])
        self.assertTrue(plan["template_binding"]["degrade_reason"])

    def test_subsystem_planner_degrades_to_atomic_when_template_inputs_are_insufficient(self):
        decomposition_result, architecture_plan = make_decomposition_and_architecture(prefer_template=True)
        descriptor = decomposition_result["subsystem_descriptors"][0]
        descriptor["interface_bindings"].append(
            {
                "signal_name": "fan_enable_feedback",
                "signal_key": "fan_enable_feedback",
                "canonical_signal_key": "fan_enable_feedback",
                "direction": "input",
                "binding_kind": "external_input",
                "allowed_external": True,
                "owner_subsystem_id": "",
                "port_index": 2,
            }
        )
        descriptor["imports"].append("fan_enable_feedback")

        with patch.object(config, "DEBUG", False):
            planner = SubsystemPlanner()
            subsystem_plan_map = planner.plan({}, decomposition_result, architecture_plan, make_bundle(include_template=True))

        plan = subsystem_plan_map["supply_fan_ctrl"]
        imported_names = [item["signal_name"] for item in plan["imported_signals"]]
        self.assertEqual(plan["implementation_mode"], "atomic_assembly")
        self.assertTrue(plan["template_binding"]["degraded"])
        self.assertEqual(plan["template_binding"]["template_id"], "fan_template")
        self.assertIn("template_input_interface_mismatch", plan["degrade_reason"])
        self.assertIn("fan_enable_feedback", imported_names)

    def test_subsystem_planner_degrades_to_atomic_when_template_outputs_are_insufficient(self):
        decomposition_result, architecture_plan = make_decomposition_and_architecture(prefer_template=True)
        descriptor = decomposition_result["subsystem_descriptors"][0]
        descriptor["interface_bindings"].append(
            {
                "signal_name": "supply_fan_status_flag",
                "signal_key": "supply_fan_status_flag",
                "canonical_signal_key": "supply_fan_status_flag",
                "direction": "output",
                "binding_kind": "subsystem_output",
                "allowed_external": False,
                "owner_subsystem_id": "",
                "port_index": 1,
            }
        )
        descriptor["exports"].append("supply_fan_status_flag")

        with patch.object(config, "DEBUG", False):
            planner = SubsystemPlanner()
            subsystem_plan_map = planner.plan({}, decomposition_result, architecture_plan, make_bundle(include_template=True))

        plan = subsystem_plan_map["supply_fan_ctrl"]
        self.assertEqual(plan["implementation_mode"], "atomic_assembly")
        self.assertTrue(plan["template_binding"]["degraded"])
        self.assertEqual(plan["template_binding"]["template_id"], "fan_template")
        self.assertIn("template_output_interface_mismatch", plan["degrade_reason"])

    def test_subsystem_planner_uses_shared_signal_registry_for_cross_subsystem_interfaces(self):
        decomposition_result, architecture_plan = make_multi_subsystem_inputs()

        with patch.object(config, "DEBUG", False):
            planner = SubsystemPlanner()
            subsystem_plan_map = planner.plan(
                {"global_modes": ["schedule_enable"]},
                decomposition_result,
                architecture_plan,
                make_bundle(include_template=True),
            )

        heater_plan = subsystem_plan_map["heater_ctrl"]
        imported_names = [item["signal_name"] for item in heater_plan["imported_signals"]]
        self.assertIn("schedule_enable", imported_names)
        self.assertIn("supply_fan_available_flag", imported_names)
        binding_kind_map = {item["signal_name"]: item["binding_kind"] for item in heater_plan["imported_signals"]}
        self.assertEqual(binding_kind_map["schedule_enable"], "external_input")
        self.assertEqual(binding_kind_map["supply_fan_available_flag"], "shared_signal")
        shared_binding = next(
            item for item in heater_plan["imported_signals"]
            if item["signal_name"] == "supply_fan_available_flag"
        )
        self.assertEqual(shared_binding["owner_subsystem_id"], "supply_fan_ctrl")
        self.assertEqual(shared_binding["resolution_status"], "resolved")
        self.assertEqual(shared_binding["candidate_exporters"], ["supply_fan_ctrl"])
        self.assertEqual(heater_plan["implementation_mode"], "atomic_assembly")
        self.assertTrue(heater_plan["selection_reason"])
        self.assertTrue(heater_plan["degrade_reason"])


if __name__ == "__main__":
    unittest.main()
