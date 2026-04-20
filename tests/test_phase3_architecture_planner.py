from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
from agents.architecture_planner import ArchitecturePlanner
from utils.ahu_knowledge_builder import build_ahu_knowledge_assets


def make_real_bundle() -> dict:
    assets = build_ahu_knowledge_assets(output_dir=None)
    pattern = assets["system_patterns"][0]
    return {
        "atomic_modules": [],
        "subflow_templates": assets["subflow_templates"],
        "system_patterns": assets["system_patterns"],
        "style_guides": [],
        "metadata": {
            "selected_case_pattern_id": pattern["pattern_id"],
            "retrieved_subflow_count": len(assets["subflow_templates"]),
            "retrieved_pattern_count": len(assets["system_patterns"]),
        },
    }


def make_requirement_spec() -> dict:
    return {
        "schema_version": "3.0",
        "system_type": "AHU",
        "scenario_summary": "AHU 送风机与直膨联动控制",
        "subsystems": [
            {
                "subsystem_id": "supply_fan_ctrl",
                "subsystem_type": "supply_fan_control",
                "goal": "送风机启停和状态管理",
                "page_hint": "控制",
                "priority": 1,
                "preferred_templates": [],
                "imports": ["schedule_enable"],
                "exports": ["supply_fan_available_flag"],
            },
            {
                "subsystem_id": "dx_ctrl",
                "subsystem_type": "dx_control",
                "goal": "直膨机组联锁控制",
                "page_hint": "控制",
                "priority": 2,
                "preferred_templates": [],
                "imports": ["supply_fan_available_flag"],
                "exports": ["dx_run_flag"],
            },
        ],
        "signals": {"inputs": [], "outputs": [], "software_points": [], "alarm_points": []},
        "required_pages": ["IO/通讯", "控制", "定时"],
        "global_modes": ["schedule_enable"],
        "ambiguities": [],
        "assumptions": [],
        "acceptance_criteria": [],
        "confidence": 0.9,
        "warnings": [],
    }


def make_competing_pattern_bundle() -> dict:
    return {
        "atomic_modules": [],
        "subflow_templates": [],
        "system_patterns": [
            {
                "pattern_id": "ahu_basic_pattern",
                "system_type": "AHU",
                "required_pages": [
                    {"page_key": "control", "label": "控制", "kind": "control"},
                    {"page_key": "io_comm", "label": "IO/通讯", "kind": "io"},
                ],
                "optional_pages": [{"page_key": "timing", "label": "定时", "kind": "timing"}],
            },
            {
                "pattern_id": "ahu_dx_pattern",
                "system_type": "AHU",
                "required_pages": [
                    {"page_key": "control", "label": "控制", "kind": "control"},
                    {"page_key": "io_comm", "label": "IO/通讯", "kind": "io"},
                    {"page_key": "dx_status", "label": "直膨机状态", "kind": "status"},
                ],
                "optional_pages": [{"page_key": "dx_fault", "label": "直膨机故障", "kind": "fault"}],
            },
        ],
        "style_guides": [],
        "metadata": {"selected_case_pattern_id": "ahu_basic_pattern"},
    }


def make_interface_semantics_bundle() -> dict:
    return {
        "atomic_modules": [],
        "subflow_templates": [
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
                        {"index": 0, "label": "送风机运行状态"},
                        {"index": 1, "label": "送风机启停手动控制命令"},
                    ],
                    "outputs": [{"index": 0, "label": "送风机可用标志"}],
                },
                "template_json": {"type": "subflow", "id": "fan_template", "name": "送风机标准控制", "inputs": 2, "outputs": 1},
                "compile_hints": {"input_count": 2, "output_count": 1},
            },
            {
                "module_type": "heater_template",
                "asset_type": "subflow_template",
                "template_id": "heater_template",
                "definition_id": "heater_template",
                "template_name": "电加热标准控制",
                "template_role": "heater_control",
                "name": "电加热标准控制",
                "category": "AHU/subflow_templates/heater_control",
                "description": "Reusable heater control subflow.",
                "parameters_schema": {},
                "ports_definition": {
                    "inputs": [
                        {"index": 0, "label": "控制使能"},
                        {"index": 1, "label": "温度设定值"},
                    ],
                    "outputs": [{"index": 0, "label": "电加热控制值"}],
                },
                "template_json": {"type": "subflow", "id": "heater_template", "name": "电加热标准控制", "inputs": 2, "outputs": 1},
                "compile_hints": {"input_count": 2, "output_count": 1},
            },
        ],
        "system_patterns": [
            {
                "pattern_id": "ahu_semantics_pattern",
                "system_type": "AHU",
                "required_pages": [
                    {"page_key": "control", "label": "控制", "kind": "control"},
                    {"page_key": "io_comm", "label": "IO/通讯", "kind": "io"},
                ],
                "optional_pages": [],
            }
        ],
        "style_guides": [],
        "metadata": {"selected_case_pattern_id": "ahu_semantics_pattern"},
    }


def make_template_interface_coverage_bundle() -> dict:
    return {
        "atomic_modules": [],
        "subflow_templates": [
            {
                "module_type": "fan_template_incomplete",
                "asset_type": "subflow_template",
                "template_id": "fan_template_incomplete",
                "definition_id": "fan_template_incomplete",
                "template_name": "送风机简化控制",
                "template_role": "supply_fan_control",
                "name": "送风机简化控制",
                "category": "AHU/subflow_templates/fan_control",
                "description": "Reusable fan control subflow with incomplete interface coverage.",
                "parameters_schema": {},
                "ports_definition": {
                    "inputs": [{"index": 0, "label": "schedule_enable"}],
                    "outputs": [],
                },
                "template_json": {
                    "type": "subflow",
                    "id": "fan_template_incomplete",
                    "name": "送风机简化控制",
                    "inputs": 1,
                    "outputs": 0,
                },
                "compile_hints": {"input_count": 1, "output_count": 0},
            },
            {
                "module_type": "fan_template_full",
                "asset_type": "subflow_template",
                "template_id": "fan_template_full",
                "definition_id": "fan_template_full",
                "template_name": "送风机标准控制",
                "template_role": "supply_fan_control",
                "name": "送风机标准控制",
                "category": "AHU/subflow_templates/fan_control",
                "description": "Reusable fan control subflow with full interface coverage.",
                "parameters_schema": {},
                "ports_definition": {
                    "inputs": [
                        {"index": 0, "label": "schedule_enable"},
                        {"index": 1, "label": "fan_fault_reset"},
                    ],
                    "outputs": [{"index": 0, "label": "supply_fan_available_flag"}],
                },
                "template_json": {
                    "type": "subflow",
                    "id": "fan_template_full",
                    "name": "送风机标准控制",
                    "inputs": 2,
                    "outputs": 1,
                },
                "compile_hints": {"input_count": 2, "output_count": 1},
            },
        ],
        "system_patterns": [
            {
                "pattern_id": "ahu_interface_coverage_pattern",
                "system_type": "AHU",
                "required_pages": [
                    {"page_key": "control", "label": "控制", "kind": "control"},
                    {"page_key": "io_comm", "label": "IO/通讯", "kind": "io"},
                ],
                "optional_pages": [],
            }
        ],
        "style_guides": [],
        "metadata": {"selected_case_pattern_id": "ahu_interface_coverage_pattern"},
    }


def make_interface_semantics_requirement_spec() -> dict:
    return {
        "schema_version": "3.0",
        "system_type": "AHU",
        "scenario_summary": "AHU 送风机与电加热联动控制",
        "subsystems": [
            {
                "subsystem_id": "supply_fan_ctrl",
                "subsystem_type": "supply_fan_control",
                "goal": "送风机控制",
                "page_hint": "控制",
                "priority": 1,
                "preferred_templates": [],
                "imports": [],
                "exports": ["supply_fan_available_flag"],
            },
            {
                "subsystem_id": "heater_ctrl",
                "subsystem_type": "heater_control",
                "goal": "电加热控制",
                "page_hint": "控制",
                "priority": 2,
                "preferred_templates": [],
                "imports": ["supply_fan_available_flag"],
                "exports": ["heater_enable"],
            },
        ],
        "signals": {"inputs": ["温度设定值"], "outputs": [], "software_points": [], "alarm_points": []},
        "required_pages": ["IO/通讯", "控制"],
        "global_modes": [],
        "ambiguities": [],
        "assumptions": [],
        "acceptance_criteria": [],
        "confidence": 0.9,
        "warnings": [],
    }


def make_minimal_pattern_bundle() -> dict:
    return {
        "atomic_modules": [],
        "subflow_templates": [],
        "system_patterns": [
            {
                "pattern_id": "ahu_minimal_pattern",
                "system_type": "AHU",
                "required_pages": [
                    {"page_key": "control", "label": "控制", "kind": "control"},
                ],
                "optional_pages": [],
            }
        ],
        "style_guides": [],
        "metadata": {"selected_case_pattern_id": "ahu_minimal_pattern"},
    }


def make_ambiguous_shared_signal_requirement_spec() -> dict:
    return {
        "schema_version": "3.0",
        "system_type": "AHU",
        "scenario_summary": "双风机与电加热联动控制",
        "subsystems": [
            {
                "subsystem_id": "supply_fan_ctrl",
                "subsystem_type": "supply_fan_control",
                "goal": "主送风机控制",
                "page_hint": "控制",
                "priority": 1,
                "preferred_templates": [],
                "imports": [],
                "exports": ["supply_fan_available_flag"],
            },
            {
                "subsystem_id": "backup_fan_ctrl",
                "subsystem_type": "supply_fan_control",
                "goal": "备用送风机控制",
                "page_hint": "控制",
                "priority": 2,
                "preferred_templates": [],
                "imports": [],
                "exports": ["supply_fan_available_flag"],
            },
            {
                "subsystem_id": "heater_ctrl",
                "subsystem_type": "heater_control",
                "goal": "电加热控制",
                "page_hint": "控制",
                "priority": 3,
                "preferred_templates": [],
                "imports": ["supply_fan_available_flag"],
                "exports": ["heater_enable"],
            },
        ],
        "signals": {"inputs": [], "outputs": [], "software_points": [], "alarm_points": []},
        "required_pages": ["控制"],
        "global_modes": [],
        "ambiguities": [],
        "assumptions": [],
        "acceptance_criteria": [],
        "confidence": 0.8,
        "warnings": [],
    }


class Phase3ArchitecturePlannerTests(unittest.TestCase):
    def test_architecture_planner_binds_real_ahu_system_pattern(self):
        bundle = make_real_bundle()

        with patch.object(config, "DEBUG", False):
            planner = ArchitecturePlanner()
            decomposition_result, architecture_plan = planner.plan(make_requirement_spec(), bundle)

        self.assertTrue(architecture_plan["pattern_bindings"])
        self.assertEqual(
            architecture_plan["pattern_bindings"][0]["pattern_id"],
            bundle["system_patterns"][0]["pattern_id"],
        )
        page_ids = {page["page_id"] for page in architecture_plan["pages"]}
        self.assertIn("page_control", page_ids)
        self.assertIn("page_io_comm", page_ids)
        self.assertIn("page_dx_status", page_ids)
        self.assertIn("page_dx_fault", page_ids)
        self.assertEqual(decomposition_result["planning_order"], ["supply_fan_ctrl", "dx_ctrl"])
        shared_signal_map = {
            item["signal_key"]: item
            for item in architecture_plan["shared_signal_registry"]
        }
        self.assertNotIn("schedule_enable", shared_signal_map)
        self.assertIn("supply_fan_available", shared_signal_map)
        self.assertEqual(shared_signal_map["supply_fan_available"]["owner_subsystem_id"], "supply_fan_ctrl")
        self.assertEqual(shared_signal_map["supply_fan_available"]["resolution_status"], "resolved")
        self.assertEqual(shared_signal_map["supply_fan_available"]["candidate_exporters"], ["supply_fan_ctrl"])
        self.assertTrue(shared_signal_map["supply_fan_available"]["resolution_evidence"])
        descriptor_map = {item["subsystem_id"]: item for item in decomposition_result["subsystem_descriptors"]}
        supply_bindings = descriptor_map["supply_fan_ctrl"]["interface_bindings"]
        self.assertTrue(
            any(
                binding["direction"] == "input"
                and binding["binding_kind"] in {"external_input", "external_command", "external_parameter"}
                and binding["allowed_external"]
                for binding in supply_bindings
            )
        )

    def test_architecture_planner_emits_slots_and_template_preferences(self):
        bundle = make_real_bundle()

        with patch.object(config, "DEBUG", False):
            planner = ArchitecturePlanner()
            decomposition_result, architecture_plan = planner.plan(make_requirement_spec(), bundle)

        slot_map = {slot["subsystem_id"]: slot for slot in architecture_plan["subsystem_slots"]}
        self.assertIn("supply_fan_ctrl", slot_map)
        self.assertIn("dx_ctrl", slot_map)
        self.assertTrue(slot_map["supply_fan_ctrl"]["preferred_template_ids"])
        self.assertEqual(slot_map["supply_fan_ctrl"]["preferred_implementation"], "reuse_template")
        self.assertTrue(slot_map["supply_fan_ctrl"]["score_breakdown"])
        self.assertTrue(slot_map["supply_fan_ctrl"]["selection_reason"])
        self.assertEqual(slot_map["supply_fan_ctrl"]["degrade_reason"], "")
        template_role_by_id = {
            item["template_id"]: item["template_role"]
            for item in bundle["subflow_templates"]
        }
        self.assertEqual(
            template_role_by_id[slot_map["supply_fan_ctrl"]["preferred_template_ids"][0]],
            "supply_fan_control",
        )
        descriptor_map = {item["subsystem_id"]: item for item in decomposition_result["subsystem_descriptors"]}
        self.assertEqual(descriptor_map["dx_ctrl"]["page_id"], slot_map["dx_ctrl"]["page_id"])

    def test_architecture_planner_scores_patterns_instead_of_blindly_trusting_selected_case_pattern(self):
        bundle = make_competing_pattern_bundle()

        with patch.object(config, "DEBUG", False):
            planner = ArchitecturePlanner()
            _, architecture_plan = planner.plan(make_requirement_spec(), bundle)

        self.assertEqual(architecture_plan["pattern_bindings"][0]["pattern_id"], "ahu_dx_pattern")
        self.assertGreater(architecture_plan["pattern_bindings"][0]["score"], 0)
        self.assertTrue(architecture_plan["pattern_bindings"][0]["score_reasons"])
        self.assertTrue(architecture_plan["pattern_bindings"][0]["score_breakdown"])
        score_breakdown = architecture_plan["pattern_bindings"][0]["score_breakdown"]
        self.assertIn("dx_control", score_breakdown["subsystem_type"])

    def test_architecture_planner_keeps_external_template_inputs_out_of_shared_signal_registry(self):
        bundle = make_interface_semantics_bundle()

        with patch.object(config, "DEBUG", False):
            planner = ArchitecturePlanner()
            decomposition_result, architecture_plan = planner.plan(make_interface_semantics_requirement_spec(), bundle)

        descriptor_map = {item["subsystem_id"]: item for item in decomposition_result["subsystem_descriptors"]}
        heater_bindings = {
            binding["signal_name"]: binding
            for binding in descriptor_map["heater_ctrl"]["interface_bindings"]
        }
        self.assertEqual(heater_bindings["控制使能"]["binding_kind"], "shared_signal")
        self.assertEqual(heater_bindings["控制使能"]["canonical_signal_key"], "supply_fan_available")
        self.assertEqual(heater_bindings["温度设定值"]["binding_kind"], "external_input")
        self.assertTrue(heater_bindings["温度设定值"]["allowed_external"])

        shared_signal_keys = {
            item["signal_key"]
            for item in architecture_plan["shared_signal_registry"]
        }
        self.assertEqual(shared_signal_keys, {"supply_fan_available"})
        registry_entry = architecture_plan["shared_signal_registry"][0]
        self.assertEqual(registry_entry["resolution_status"], "resolved")
        self.assertEqual(registry_entry["candidate_exporters"], ["supply_fan_ctrl"])

    def test_architecture_planner_prefers_templates_with_complete_interface_coverage(self):
        bundle = make_template_interface_coverage_bundle()
        requirement_spec = {
            "schema_version": "3.0",
            "system_type": "AHU",
            "scenario_summary": "送风机控制",
            "subsystems": [
                {
                    "subsystem_id": "supply_fan_ctrl",
                    "subsystem_type": "supply_fan_control",
                    "goal": "送风机控制",
                    "page_hint": "控制",
                    "priority": 1,
                    "preferred_templates": [],
                    "imports": ["schedule_enable", "fan_fault_reset"],
                    "exports": ["supply_fan_available_flag"],
                }
            ],
            "signals": {"inputs": [], "outputs": [], "software_points": [], "alarm_points": []},
            "required_pages": ["IO/通讯", "控制"],
            "global_modes": ["schedule_enable"],
            "ambiguities": [],
            "assumptions": [],
            "acceptance_criteria": [],
            "confidence": 0.9,
            "warnings": [],
        }

        with patch.object(config, "DEBUG", False):
            planner = ArchitecturePlanner()
            decomposition_result, architecture_plan = planner.plan(requirement_spec, bundle)

        slot = architecture_plan["subsystem_slots"][0]
        self.assertEqual(slot["preferred_implementation"], "reuse_template")
        self.assertEqual(slot["preferred_template_ids"][0], "fan_template_full")
        top_score_cards = {item["template_id"]: item for item in slot["score_breakdown"]}
        self.assertGreater(top_score_cards["fan_template_full"]["score"], top_score_cards["fan_template_incomplete"]["score"])
        incomplete_breakdown = top_score_cards["fan_template_incomplete"]["score_breakdown"]
        self.assertEqual(incomplete_breakdown["interface_capacity"]["input_shortage"], 1)
        self.assertEqual(incomplete_breakdown["interface_capacity"]["output_shortage"], 1)
        descriptor = decomposition_result["subsystem_descriptors"][0]
        self.assertEqual(descriptor["imports"], ["schedule_enable", "fan_fault_reset"])
        self.assertEqual(descriptor["exports"], ["supply_fan_available_flag"])

    def test_architecture_planner_marks_ambiguous_shared_signal_with_candidate_exporters(self):
        bundle = make_minimal_pattern_bundle()

        with patch.object(config, "DEBUG", False):
            planner = ArchitecturePlanner()
            _, architecture_plan = planner.plan(make_ambiguous_shared_signal_requirement_spec(), bundle)

        registry_entry = architecture_plan["shared_signal_registry"][0]
        self.assertEqual(registry_entry["signal_key"], "supply_fan_available")
        self.assertEqual(registry_entry["resolution_status"], "ambiguous")
        self.assertEqual(
            registry_entry["candidate_exporters"],
            ["backup_fan_ctrl", "supply_fan_ctrl"],
        )
        self.assertFalse(registry_entry["owner_subsystem_id"])
        self.assertTrue(registry_entry["resolution_evidence"])

    def test_architecture_planner_emits_native_interface_bindings_and_candidate_exporters(self):
        bundle = make_real_bundle()

        with patch.object(config, "DEBUG", False):
            planner = ArchitecturePlanner()
            decomposition_result, architecture_plan = planner.plan(make_requirement_spec(), bundle)

        for descriptor in decomposition_result["subsystem_descriptors"]:
            self.assertIn("interface_bindings", descriptor)
            self.assertTrue(descriptor["interface_bindings"])
            for binding in descriptor["interface_bindings"]:
                self.assertIn("direction", binding)
                self.assertIn("binding_kind", binding)
                self.assertIn("canonical_signal_key", binding)

        for entry in architecture_plan["shared_signal_registry"]:
            self.assertIn("candidate_exporters", entry)
            self.assertNotIn("exporter_candidates", entry)
            self.assertIn("resolution_status", entry)


if __name__ == "__main__":
    unittest.main()
