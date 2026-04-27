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
from agents.llm_enhancers.architecture_advisor import ArchitectureAdvice, ArchitectureAdvisor
from tests.test_phase3_architecture_planner import (
    make_ambiguous_shared_signal_requirement_spec,
    make_interface_semantics_bundle,
    make_interface_semantics_requirement_spec,
    make_minimal_pattern_bundle,
    make_requirement_spec,
    make_template_interface_coverage_bundle,
)


class FakeStructuredLLM:
    def __init__(self, payload=None, error: Exception | None = None):
        self.payload = payload
        self.error = error

    def invoke(self, _messages):
        if self.error:
            raise self.error
        if isinstance(self.payload, ArchitectureAdvice):
            return self.payload
        return ArchitectureAdvice(**(self.payload or {}))


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


def make_planner(payload=None, structured_error: Exception | None = None, invoke_error: Exception | None = None) -> ArchitecturePlanner:
    advisor = ArchitectureAdvisor(
        llm=FakeLLM(payload=payload, structured_error=structured_error, invoke_error=invoke_error),
        provider="fake",
        model="fake-architecture",
    )
    return ArchitecturePlanner(architecture_advisor=advisor)


class ArchitectureLlmAdvisorTests(unittest.TestCase):
    def run_planner(self, planner: ArchitecturePlanner, requirement_spec: dict, retrieval_bundle: dict):
        with (
            patch.object(config, "DEBUG", False),
            patch.object(config, "LLM_ENHANCEMENT_ENABLED", True),
            patch.object(config, "ARCHITECTURE_USE_LLM_ADVISOR", True),
        ):
            return planner.plan(requirement_spec, retrieval_bundle)

    def test_llm_advisor_adds_dx_status_page(self):
        payload = {
            "page_patch": [
                {
                    "label": "直膨机状态",
                    "kind": "status",
                    "reason": "需求包含直膨机组状态展示。",
                }
            ],
            "confidence": 0.9,
        }

        decomposition_result, architecture_plan = self.run_planner(
            make_planner(payload),
            make_requirement_spec(),
            make_minimal_pattern_bundle(),
        )

        labels = {page["label"] for page in architecture_plan["pages"]}
        self.assertIn("直膨机状态", labels)
        self.assertEqual(decomposition_result["pages"], architecture_plan["pages"])
        advisory = architecture_plan["pattern_bindings"][0]["llm_advisory"]
        self.assertTrue(advisory["enabled"])
        self.assertTrue(advisory["adopted"])
        self.assertEqual(advisory["patch_count"], 1)

    def test_llm_advisor_reorders_template_preferences_with_allowed_ids_only(self):
        payload = {
            "template_preferences": {
                "supply_fan_ctrl": ["fan_template_incomplete", "fan_template_full"],
            },
            "confidence": 0.8,
        }
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

        _, architecture_plan = self.run_planner(
            make_planner(payload),
            requirement_spec,
            make_template_interface_coverage_bundle(),
        )

        slot = architecture_plan["subsystem_slots"][0]
        self.assertEqual(slot["preferred_template_ids"][0], "fan_template_incomplete")
        self.assertEqual(slot["preferred_implementation"], "reuse_template")
        self.assertEqual(slot["score_breakdown"][0]["score_breakdown"]["llm_advisor"]["score"], 1)
        advisory = architecture_plan["pattern_bindings"][0]["llm_advisory"]
        self.assertTrue(advisory["adopted"])

    def test_llm_advisor_rejects_required_page_deletion(self):
        payload = {
            "page_patch": [
                {
                    "action": "delete",
                    "label": "控制",
                }
            ],
            "warnings": ["不应删除控制页"],
        }

        _, architecture_plan = self.run_planner(
            make_planner(payload),
            make_requirement_spec(),
            make_minimal_pattern_bundle(),
        )

        labels = {page["label"] for page in architecture_plan["pages"]}
        self.assertIn("控制", labels)
        advisory = architecture_plan["pattern_bindings"][0]["llm_advisory"]
        self.assertFalse(advisory["adopted"])
        self.assertEqual(advisory["rejected_patch_count"], 1)
        self.assertTrue(any("rejected deletion" in item for item in advisory["warnings"]))

    def test_llm_advisor_rejects_unknown_template_id(self):
        payload = {
            "template_preferences": {
                "heater_ctrl": ["missing_template"],
            },
        }

        _, architecture_plan = self.run_planner(
            make_planner(payload),
            make_interface_semantics_requirement_spec(),
            make_interface_semantics_bundle(),
        )

        slot_map = {slot["subsystem_id"]: slot for slot in architecture_plan["subsystem_slots"]}
        self.assertNotIn("missing_template", slot_map["heater_ctrl"]["preferred_template_ids"])
        advisory = architecture_plan["pattern_bindings"][0]["llm_advisory"]
        self.assertFalse(advisory["adopted"])
        self.assertEqual(advisory["rejected_patch_count"], 1)
        self.assertTrue(any("missing_template" in item for item in advisory["warnings"]))

    def test_llm_shared_signal_multi_owner_stays_warning_only(self):
        payload = {
            "shared_signal_patch": [
                {
                    "signal_name": "supply_fan_available_flag",
                    "candidate_exporters": ["supply_fan_ctrl", "backup_fan_ctrl"],
                }
            ],
        }

        _, architecture_plan = self.run_planner(
            make_planner(payload),
            make_ambiguous_shared_signal_requirement_spec(),
            make_minimal_pattern_bundle(),
        )

        registry_entry = architecture_plan["shared_signal_registry"][0]
        self.assertEqual(registry_entry["resolution_status"], "ambiguous")
        self.assertFalse(registry_entry["owner_subsystem_id"])
        advisory = architecture_plan["pattern_bindings"][0]["llm_advisory"]
        self.assertFalse(advisory["adopted"])
        self.assertEqual(advisory["rejected_patch_count"], 1)
        self.assertTrue(any("ambiguous owner" in item for item in advisory["warnings"]))

    def test_llm_failure_keeps_deterministic_architecture(self):
        planner = make_planner(
            payload={},
            structured_error=RuntimeError("structured failed"),
            invoke_error=RuntimeError("raw failed"),
        )

        _, architecture_plan = self.run_planner(
            planner,
            make_requirement_spec(),
            make_minimal_pattern_bundle(),
        )

        labels = {page["label"] for page in architecture_plan["pages"]}
        self.assertIn("控制", labels)
        advisory = architecture_plan["pattern_bindings"][0]["llm_advisory"]
        self.assertFalse(advisory["adopted"])
        self.assertTrue(advisory["fallback_used"])
        self.assertIn("raw failed", advisory["fallback_reason"])

    def test_switch_off_keeps_previous_architecture_shape(self):
        planner = make_planner(
            {
                "page_patch": [
                    {
                        "label": "直膨机状态",
                        "kind": "status",
                    }
                ],
            }
        )
        with (
            patch.object(config, "DEBUG", False),
            patch.object(config, "LLM_ENHANCEMENT_ENABLED", False),
            patch.object(config, "ARCHITECTURE_USE_LLM_ADVISOR", True),
        ):
            _, architecture_plan = planner.plan(make_requirement_spec(), make_minimal_pattern_bundle())

        labels = {page["label"] for page in architecture_plan["pages"]}
        self.assertNotIn("直膨机状态", labels)
        self.assertNotIn("llm_advisory", architecture_plan["pattern_bindings"][0])


if __name__ == "__main__":
    unittest.main()
