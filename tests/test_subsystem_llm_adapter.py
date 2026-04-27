from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
from agents.llm_enhancers.subsystem_interface_adapter import (
    SubsystemInterfaceAdapter,
    SubsystemInterfaceAdvice,
)
from agents.subsystem_planner import SubsystemPlanner
from tests.test_phase3_subsystem_planner import make_bundle, make_decomposition_and_architecture


class FakeStructuredLLM:
    def __init__(self, payload=None, error: Exception | None = None):
        self.payload = payload
        self.error = error

    def invoke(self, _messages):
        if self.error:
            raise self.error
        if isinstance(self.payload, SubsystemInterfaceAdvice):
            return self.payload
        return SubsystemInterfaceAdvice(**(self.payload or {}))


class FakeLLM:
    def __init__(self, payload=None, structured_error: Exception | None = None, invoke_error: Exception | None = None):
        self.payload = payload
        self.structured_error = structured_error
        self.invoke_error = invoke_error

    def with_structured_output(self, *_args, **_kwargs):
        return FakeStructuredLLM(self.payload, self.structured_error)

    def invoke(self, _messages):
        if self.invoke_error:
            raise self.invoke_error

        class Response:
            content = "{}"

        return Response()


def make_planner(payload=None, structured_error: Exception | None = None, invoke_error: Exception | None = None) -> SubsystemPlanner:
    adapter = SubsystemInterfaceAdapter(
        llm=FakeLLM(payload=payload, structured_error=structured_error, invoke_error=invoke_error),
        provider="fake",
        model="fake-subsystem",
    )
    return SubsystemPlanner(interface_adapter=adapter)


class SubsystemLlmAdapterTests(unittest.TestCase):
    def run_planner(self, planner: SubsystemPlanner, decomposition_result: dict | None = None, architecture_plan: dict | None = None):
        if decomposition_result is None or architecture_plan is None:
            decomposition_result, architecture_plan = make_decomposition_and_architecture(prefer_template=True)
        with (
            patch.object(config, "DEBUG", False),
            patch.object(config, "LLM_ENHANCEMENT_ENABLED", True),
            patch.object(config, "SUBSYSTEM_USE_LLM_ADAPTER", True),
        ):
            return planner.plan({}, decomposition_result, architecture_plan, make_bundle(include_template=True))

    def test_planner_adopts_fake_llm_port_binding_patch(self):
        decomposition_result, architecture_plan = make_decomposition_and_architecture(prefer_template=True)
        descriptor = decomposition_result["subsystem_descriptors"][0]
        descriptor["interface_bindings"][0]["signal_name"] = "wrong_signal"
        descriptor["interface_bindings"][0]["signal_key"] = "wrong_signal"
        descriptor["interface_bindings"][0]["canonical_signal_key"] = "wrong_signal"
        payload = {
            "subsystem_id": "supply_fan_ctrl",
            "selected_template_id": "fan_template",
            "port_binding_patch": [
                {
                    "direction": "input",
                    "port_index": 0,
                    "template_port_name": "schedule_enable",
                    "signal_name": "送风机启停自动命令",
                    "binding_kind": "external_input",
                    "allowed_external": True,
                    "confidence": 0.92,
                    "reason": "端口语义是送风机启停使能。",
                }
            ],
        }

        subsystem_plan_map = self.run_planner(make_planner(payload), decomposition_result, architecture_plan)

        plan = subsystem_plan_map["supply_fan_ctrl"]
        self.assertEqual(plan["implementation_mode"], "reuse_template")
        self.assertEqual(plan["imported_signals"][0]["signal_name"], "送风机启停自动命令")
        advisory = plan["template_binding"]["llm_advisory"]
        self.assertTrue(advisory["enabled"])
        self.assertTrue(advisory["adopted"])
        self.assertEqual(advisory["patch_count"], 1)
        self.assertEqual(advisory["rejected_patch_count"], 0)

    def test_planner_rejects_out_of_range_port_patch(self):
        payload = {
            "subsystem_id": "supply_fan_ctrl",
            "selected_template_id": "fan_template",
            "port_binding_patch": [
                {
                    "direction": "input",
                    "port_index": 99,
                    "signal_name": "越界信号",
                    "binding_kind": "external_input",
                    "allowed_external": True,
                    "confidence": 0.95,
                }
            ],
        }

        subsystem_plan_map = self.run_planner(make_planner(payload))

        plan = subsystem_plan_map["supply_fan_ctrl"]
        self.assertEqual(plan["implementation_mode"], "reuse_template")
        self.assertEqual(plan["imported_signals"][0]["signal_name"], "schedule_enable")
        advisory = plan["template_binding"]["llm_advisory"]
        self.assertFalse(advisory["adopted"])
        self.assertEqual(advisory["patch_count"], 0)
        self.assertEqual(advisory["rejected_patch_count"], 1)

    def test_planner_rejects_unknown_selected_template_id(self):
        payload = {
            "subsystem_id": "supply_fan_ctrl",
            "selected_template_id": "missing_template",
            "port_binding_patch": [
                {
                    "direction": "input",
                    "port_index": 0,
                    "signal_name": "送风机启停自动命令",
                    "binding_kind": "external_input",
                    "allowed_external": True,
                    "confidence": 0.9,
                }
            ],
        }

        subsystem_plan_map = self.run_planner(make_planner(payload))

        plan = subsystem_plan_map["supply_fan_ctrl"]
        self.assertEqual(plan["imported_signals"][0]["signal_name"], "schedule_enable")
        advisory = plan["template_binding"]["llm_advisory"]
        self.assertFalse(advisory["adopted"])
        self.assertIn("invalid_selected_template_id:missing_template", advisory["risk_flags"])
        self.assertEqual(advisory["rejected_patch_count"], 1)

    def test_fallback_required_does_not_force_atomic_when_template_matches(self):
        payload = {
            "subsystem_id": "supply_fan_ctrl",
            "selected_template_id": "fan_template",
            "fallback_required": True,
            "fallback_reason": "模型认为模板语义不充分，但没有合同错误。",
            "risk_flags": ["template_semantic_risk"],
        }

        subsystem_plan_map = self.run_planner(make_planner(payload))

        plan = subsystem_plan_map["supply_fan_ctrl"]
        self.assertEqual(plan["implementation_mode"], "reuse_template")
        advisory = plan["template_binding"]["llm_advisory"]
        self.assertFalse(advisory["adopted"])
        self.assertTrue(advisory["fallback_required"])
        self.assertIn("template_semantic_risk", advisory["risk_flags"])
        self.assertIn("fallback_required", advisory["risk_flags"])

    def test_llm_failure_keeps_deterministic_path(self):
        planner = make_planner(
            payload={},
            structured_error=RuntimeError("structured failed"),
            invoke_error=RuntimeError("raw failed"),
        )

        subsystem_plan_map = self.run_planner(planner)

        plan = subsystem_plan_map["supply_fan_ctrl"]
        self.assertEqual(plan["implementation_mode"], "reuse_template")
        self.assertEqual(plan["imported_signals"][0]["signal_name"], "schedule_enable")
        advisory = plan["template_binding"]["llm_advisory"]
        self.assertTrue(advisory["enabled"])
        self.assertFalse(advisory["adopted"])
        self.assertTrue(advisory["fallback_used"])
        self.assertIn("raw failed", advisory["fallback_reason"])

    def test_switch_off_keeps_previous_subsystem_planner_shape(self):
        planner = make_planner(
            payload={
                "subsystem_id": "supply_fan_ctrl",
                "selected_template_id": "fan_template",
                "port_binding_patch": [
                    {
                        "direction": "input",
                        "port_index": 0,
                        "signal_name": "不应采用",
                        "binding_kind": "external_input",
                        "allowed_external": True,
                        "confidence": 0.95,
                    }
                ],
            }
        )
        decomposition_result, architecture_plan = make_decomposition_and_architecture(prefer_template=True)

        with (
            patch.object(config, "DEBUG", False),
            patch.object(config, "LLM_ENHANCEMENT_ENABLED", False),
            patch.object(config, "SUBSYSTEM_USE_LLM_ADAPTER", True),
        ):
            subsystem_plan_map = planner.plan({}, decomposition_result, architecture_plan, make_bundle(include_template=True))

        plan = subsystem_plan_map["supply_fan_ctrl"]
        self.assertEqual(plan["imported_signals"][0]["signal_name"], "schedule_enable")
        self.assertNotIn("llm_advisory", plan["template_binding"])


if __name__ == "__main__":
    unittest.main()
