from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.analysis_agent import AnalysisAgent
from utils.phase3_adapters import build_requirement_spec


def make_complete_analysis_result() -> dict:
    return {
        "retrieval_plan": {"queries": ["AHU 送风机 冷水阀 控制"]},
        "scenario_analysis": {
            "summary": "AHU 送风机与冷水阀联动控制",
            "business_goal": "实现送风机启停和冷水阀调节",
            "system_type": "AHU",
            "equipment_object": "空调机组",
            "actuator": "送风机、冷水阀",
            "controlled_variable": "送风温度",
            "feedback_variable": "送风温度",
            "setpoint_variable": "送风温度设定值",
            "output_signal": "送风机启停命令、冷水阀开度命令",
            "control_strategy": "PID + 联锁",
            "control_mode": "手/自动，季节切换，定时启停",
            "input_signals": ["送风温度", "送风机运行状态"],
            "output_signals": ["送风机启停命令", "冷水阀开度命令"],
            "operating_conditions": ["夏季", "定时启停"],
            "interlocks_or_limits": ["送风机故障联锁", "故障报警"],
            "calculation_logic": [],
            "ambiguities": [],
            "assumptions": [],
            "confidence": 0.82,
        },
        "metadata": {"llm_used": False, "cached": False, "fallback_used": False},
    }


class Phase3RequirementSpecTests(unittest.TestCase):
    def test_build_requirement_spec_projects_complete_scenario(self):
        requirement_spec = build_requirement_spec(make_complete_analysis_result())

        self.assertEqual(requirement_spec["system_type"], "AHU")
        self.assertEqual(requirement_spec["scenario_summary"], "AHU 送风机与冷水阀联动控制")
        subsystem_ids = {item["subsystem_id"] for item in requirement_spec["subsystems"]}
        self.assertIn("supply_fan_ctrl", subsystem_ids)
        self.assertIn("chw_valve_ctrl", subsystem_ids)
        self.assertIn("IO/通讯", requirement_spec["required_pages"])
        self.assertIn("控制", requirement_spec["required_pages"])
        self.assertIn("auto_manual", requirement_spec["global_modes"])
        self.assertIn("schedule_enable", requirement_spec["global_modes"])
        self.assertIn("送风机故障联锁", requirement_spec["signals"]["alarm_points"])

    def test_build_requirement_spec_records_warning_when_information_is_insufficient(self):
        analysis_result = {
            "scenario_analysis": {
                "summary": "需要一个楼控控制逻辑",
                "system_type": "AHU",
                "ambiguities": [],
                "assumptions": [],
                "confidence": 0.3,
            }
        }

        requirement_spec = build_requirement_spec(analysis_result)

        self.assertEqual(requirement_spec["subsystems"], [])
        self.assertTrue(requirement_spec["warnings"])
        self.assertTrue(requirement_spec["ambiguities"])

    def test_analysis_agent_call_populates_requirement_spec(self):
        analysis_result = make_complete_analysis_result()
        agent = AnalysisAgent.__new__(AnalysisAgent)
        agent.analyze = lambda query: analysis_result

        state = {"user_query": "AHU 送风机与冷水阀联动控制"}
        result = agent.__call__(state)

        self.assertIsNot(result["analysis_result"], analysis_result)
        self.assertIn("clarification_signals", result["analysis_result"])
        self.assertIn("requirement_spec", result)
        self.assertEqual(result["requirement_spec"]["system_type"], "AHU")
        self.assertEqual(result["current_step"], "analysis_completed")


if __name__ == "__main__":
    unittest.main()
