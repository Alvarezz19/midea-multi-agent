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
        self.assertIn("schedule_enable", shared_signal_map)
        self.assertTrue(shared_signal_map["schedule_enable"]["allowed_external"])
        self.assertEqual(shared_signal_map["schedule_enable"]["required_exporter_count"], 0)
        self.assertIn("dx_run_flag", shared_signal_map)
        self.assertEqual(shared_signal_map["dx_run_flag"]["owner_subsystem_id"], "dx_ctrl")

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


if __name__ == "__main__":
    unittest.main()
