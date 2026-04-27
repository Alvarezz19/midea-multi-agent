from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
from agents.analysis_agent import AnalysisAgent, derive_clarification_signals
from agents.llm_enhancers.analysis_engineering_compiler import EngineeringRequirementCompiler
from utils.phase3_adapters import build_requirement_spec, merge_engineering_requirement_patch


class FakeStructuredResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def model_dump(self) -> dict:
        return json.loads(json.dumps(self.payload, ensure_ascii=False))


class FakeStructuredLLM:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def invoke(self, messages) -> FakeStructuredResponse:
        del messages
        return FakeStructuredResponse(self.payload)


class FakePatchLLM:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def with_structured_output(self, schema, method="function_calling") -> FakeStructuredLLM:
        del schema, method
        return FakeStructuredLLM(self.payload)

    def invoke(self, messages):
        del messages
        return type("FakeResponse", (), {"content": json.dumps(self.payload, ensure_ascii=False)})()


class FailingLLM:
    def with_structured_output(self, schema, method="function_calling"):
        del schema, method
        raise RuntimeError("structured boom")

    def invoke(self, messages):
        del messages
        raise RuntimeError("invoke boom")


def base_analysis_result() -> dict:
    return {
        "retrieval_plan": {"queries": ["AHU 控制"]},
        "scenario_analysis": {
            "summary": "生成 AHU 控制程序",
            "business_goal": "实现空调箱控制",
            "system_type": "AHU",
            "equipment_object": "空调箱",
            "actuator": "",
            "controlled_variable": "",
            "feedback_variable": "",
            "setpoint_variable": "",
            "output_signal": "",
            "control_strategy": "",
            "control_mode": "",
            "input_signals": [],
            "output_signals": [],
            "operating_conditions": [],
            "interlocks_or_limits": [],
            "calculation_logic": [],
            "ambiguities": [],
            "assumptions": [],
            "confidence": 0.65,
        },
        "metadata": {"llm_used": False, "cached": False, "fallback_used": False},
    }


def ahu_patch() -> dict:
    return {
        "system_type": "AHU",
        "project_summary": "AHU 送风机、冷水阀、电加热和直膨联动控制",
        "subsystem_patches": [
            {
                "subsystem_id": "supply_fan_ctrl",
                "subsystem_type": "supply_fan_control",
                "goal": "送风机启停与频率控制",
                "page_hint": "控制",
                "imports": ["送风机故障状态"],
                "exports": ["送风机启停命令"],
            },
            {
                "subsystem_id": "chw_valve_ctrl",
                "subsystem_type": "chw_valve_control",
                "goal": "冷水阀 PID 调节",
                "page_hint": "控制",
                "imports": ["送风温度"],
                "exports": ["冷水阀开度命令"],
            },
        ],
        "required_pages": ["IO/通讯", "控制", "定时", "直膨机状态"],
        "global_modes": ["auto_manual", "schedule_enable"],
        "points": [
            {
                "name": "送风温度",
                "point_role": "sensor",
                "subsystem_id": "chw_valve_ctrl",
                "io_kind": "physical_input",
                "explicit": True,
                "confidence": 0.9,
            },
            {
                "name": "冷水阀开度命令",
                "point_role": "command",
                "subsystem_id": "chw_valve_ctrl",
                "io_kind": "physical_output",
                "explicit": True,
                "confidence": 0.9,
            },
            {
                "name": "送风温度设定值",
                "point_role": "setpoint",
                "subsystem_id": "chw_valve_ctrl",
                "io_kind": "software_point",
                "explicit": False,
                "confidence": 0.7,
            },
        ],
        "control_loops": [
            {
                "loop_id": "chw_supply_air_temp_pid",
                "subsystem_id": "chw_valve_ctrl",
                "target": "送风温度",
                "strategy": "pid",
                "pv_signal": "送风温度",
                "sp_signal": "送风温度设定值",
                "mv_signal": "冷水阀开度命令",
                "constraints": ["上下限", "死区", "计算间隔"],
                "explicit": True,
                "confidence": 0.88,
            }
        ],
        "interlocks": [
            {
                "interlock_id": "fan_fault_stop",
                "subsystem_id": "supply_fan_ctrl",
                "condition": "送风机故障",
                "action": "停止送风机并报警",
                "severity": "alarm",
                "explicit": True,
                "confidence": 0.9,
            }
        ],
        "communication": {"protocol": "modbus", "address_policy": "用户未给出地址时不编造"},
        "naming_convention": {"prefix": "AHU"},
        "acceptance_criteria": ["PID 回路包含 PV/SP/MV"],
        "ambiguities": ["未给出设备数量"],
        "assumptions": ["按单台 AHU 处理"],
        "missing_required_fields": [
            "missing_equipment_quantity",
            "missing_point_schedule",
            "missing_communication_address",
        ],
        "confidence": 0.86,
    }


class AnalysisEngineeringCompilerTests(unittest.TestCase):
    def test_merge_engineering_patch_extends_requirement_spec(self):
        requirement_spec = build_requirement_spec(base_analysis_result())

        merged = merge_engineering_requirement_patch(requirement_spec, ahu_patch())

        subsystem_ids = {item["subsystem_id"] for item in merged["subsystems"]}
        self.assertIn("supply_fan_ctrl", subsystem_ids)
        self.assertIn("chw_valve_ctrl", subsystem_ids)
        self.assertIn("直膨机状态", merged["required_pages"])
        self.assertIn("auto_manual", merged["global_modes"])
        self.assertIn("送风温度", merged["signals"]["inputs"])
        self.assertIn("冷水阀开度命令", merged["signals"]["outputs"])
        self.assertIn("送风温度设定值", merged["signals"]["software_points"])
        self.assertIn("送风机故障", merged["signals"]["alarm_points"])
        self.assertEqual(len(merged["engineering"]["points"]), 3)
        self.assertEqual(len(merged["engineering"]["control_loops"]), 1)
        self.assertEqual(len(merged["engineering"]["interlocks"]), 1)
        self.assertIn("missing_point_schedule", merged["engineering"]["missing_required_fields"])

    def test_analysis_agent_call_uses_engineering_compiler_when_enabled(self):
        agent = AnalysisAgent.__new__(AnalysisAgent)
        agent.analyze = lambda query: base_analysis_result()
        agent.engineering_compiler = EngineeringRequirementCompiler(FakePatchLLM(ahu_patch()), provider="fake", model="fake-model")

        with patch.object(config, "ANALYSIS_USE_ENGINEERING_COMPILER", True):
            result = agent.__call__({"user_query": "生成 AHU 控制程序"})

        self.assertTrue(result["analysis_result"]["engineering_analysis"]["llm_used"])
        self.assertTrue(result["analysis_result"]["engineering_analysis"]["adopted"])
        self.assertIn("engineering", result["requirement_spec"])
        self.assertTrue(result["analysis_result"]["clarification_signals"]["should_clarify"])
        codes = {item["code"] for item in result["analysis_result"]["clarification_signals"]["signals"]}
        self.assertIn("missing_point_schedule", codes)
        self.assertIn("missing_communication_address", codes)

    def test_empty_patch_does_not_turn_math_query_into_ahu(self):
        analysis_result = {
            "scenario_analysis": {
                "summary": "计算两个数相加",
                "system_type": "",
                "ambiguities": [],
                "assumptions": [],
                "confidence": 0.8,
            }
        }
        agent = AnalysisAgent.__new__(AnalysisAgent)
        agent.analyze = lambda query: analysis_result
        agent.engineering_compiler = EngineeringRequirementCompiler(FakePatchLLM({"confidence": 0.0}), provider="fake", model="fake-model")

        with patch.object(config, "ANALYSIS_USE_ENGINEERING_COMPILER", True):
            result = agent.__call__({"user_query": "计算两个数相加"})

        self.assertEqual(result["requirement_spec"]["system_type"], "")
        self.assertNotIn("engineering", result["requirement_spec"])
        self.assertFalse(result["analysis_result"]["engineering_analysis"]["adopted"])

    def test_engineering_compiler_failure_falls_back_to_baseline_spec(self):
        agent = AnalysisAgent.__new__(AnalysisAgent)
        agent.analyze = lambda query: base_analysis_result()
        agent.engineering_compiler = EngineeringRequirementCompiler(FailingLLM(), provider="fake", model="fake-model")

        with patch.object(config, "ANALYSIS_USE_ENGINEERING_COMPILER", True):
            result = agent.__call__({"user_query": "生成 AHU 控制程序"})

        self.assertNotIn("engineering", result["requirement_spec"])
        self.assertTrue(result["analysis_result"]["engineering_analysis"]["fallback_used"])
        self.assertFalse(result["analysis_result"]["engineering_analysis"]["adopted"])

    def test_clarification_signals_include_engineering_missing_fields(self):
        requirement_spec = build_requirement_spec(base_analysis_result())
        requirement_spec = merge_engineering_requirement_patch(requirement_spec, ahu_patch())

        signals = derive_clarification_signals(base_analysis_result(), requirement_spec)
        codes = {item["code"] for item in signals["signals"]}

        self.assertTrue(signals["should_clarify"])
        self.assertIn("missing_equipment_quantity", codes)
        self.assertIn("missing_point_schedule", codes)
        self.assertIn("missing_communication_address", codes)


if __name__ == "__main__":
    unittest.main()
