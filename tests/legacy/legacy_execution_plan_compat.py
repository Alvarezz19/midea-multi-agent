from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.legacy_execution_plan import build_legacy_execution_plan as build_legacy_execution_plan_canonical


def make_requirement_spec() -> dict:
    return {
        "scenario_summary": "送风机与加热联动",
    }


def make_architecture_plan() -> dict:
    return {
        "goal": "多子系统联动",
        "subsystem_slots": [
            {"subsystem_id": "supply_fan_ctrl"},
            {"subsystem_id": "heater_ctrl"},
        ],
    }


def make_subsystem_plan_map() -> dict:
    return {
        "supply_fan_ctrl": {
            "node_instances": [
                {
                    "logic_id": "fan_main",
                    "module_type": "constInput",
                    "parameters": {"name": "送风机"},
                    "reasoning": "主送风机节点",
                }
            ],
            "edges": [],
        },
        "heater_ctrl": {
            "node_instances": [
                {
                    "logic_id": "heater_main",
                    "module_type": "logic",
                    "parameters": {"name": "加热启停"},
                    "reasoning": "加热控制节点",
                }
            ],
            "edges": [
                {
                    "from_node": "heater_main",
                    "from_port": 0,
                    "to_node": "heater_main",
                    "to_port": 1,
                }
            ],
        },
    }


class LegacyExecutionPlanTests(unittest.TestCase):
    def test_canonical_legacy_helper_builds_flat_projection(self):
        result = build_legacy_execution_plan_canonical(
            make_requirement_spec(),
            make_architecture_plan(),
            make_subsystem_plan_map(),
        )

        self.assertEqual(result["goal"], "多子系统联动")
        self.assertEqual([node["logic_id"] for node in result["nodes"]], ["fan_main", "heater_main"])
        self.assertEqual(len(result["connections"]), 1)
        self.assertEqual(result["connections"][0]["from_node"], "heater_main")
        self.assertEqual(result["connections"][0]["to_port_index"], 1)

    def test_legacy_helper_reports_empty_projection_as_planning_failure(self):
        result = build_legacy_execution_plan_canonical(
            {"scenario_summary": "空计划"},
            {"goal": ""},
            {},
        )

        self.assertEqual(result["goal"], "规划失败: Phase 3 未生成任何子系统计划")
        self.assertEqual(result["nodes"], [])
        self.assertEqual(result["connections"], [])


if __name__ == "__main__":
    unittest.main()
