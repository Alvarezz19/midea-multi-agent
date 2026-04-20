from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
from agents.planning_agent import PlanIR, PlanningAgent


def make_bundle(include_subflow: bool = True) -> dict:
    bundle = {
        "atomic_modules": [
            {
                "module_type": "constInput",
                "name": "Constant Input",
                "category": "logic/basic",
                "description": "Provide a constant numeric value.",
                "parameters_schema": {
                    "fixedValue": {"type": "number", "description": "constant value"}
                },
                "ports_definition": {
                    "inputs": [],
                    "outputs": [
                        {
                            "index": 0,
                            "label": "out",
                            "type": "number",
                            "description": "output",
                        }
                    ],
                },
                "template_json": {"type": "constInput", "inputs": 0, "outputs": 1},
                "similarity_score": 0.91,
                "rank": 1,
            }
        ],
        "subflow_templates": [],
        "system_patterns": [
            {
                "pattern_id": "ahu_ctrl__v1",
                "pattern_name": "AHU control skeleton",
                "system_type": "AHU",
                "required_pages": [
                    {"page_key": "control", "label": "Control", "kind": "control"}
                ],
                "optional_pages": [
                    {"page_key": "timing", "label": "Timing", "kind": "timing"}
                ],
            }
        ],
        "style_guides": [],
        "metadata": {
            "query_text": "fan control",
            "query_variants": ["fan control", "supply fan control"],
            "intent": "general_query",
            "detected_operations": [],
            "selected_case_pattern_id": "ahu_ctrl__v1",
            "retrieved_atomic_count": 1,
            "retrieved_subflow_count": 0,
            "retrieved_pattern_count": 1,
            "avg_atomic_score": 0.91,
            "query_bundle_version": "phase2-v1",
        },
    }
    if include_subflow:
        bundle["subflow_templates"] = [
            {
                "module_type": "fan_template",
                "asset_type": "subflow_template",
                "template_id": "fan_template",
                "definition_id": "fan_template",
                "template_name": "Fan Template",
                "name": "Fan Template",
                "category": "AHU/subflow_templates/fan_control",
                "description": "Reusable fan control subflow.",
                "parameters_schema": {},
                "ports_definition": {
                    "inputs": [
                        {
                            "index": 0,
                            "label": "run_cmd",
                            "type": "bool",
                            "description": "run command",
                        }
                    ],
                    "outputs": [
                        {
                            "index": 0,
                            "label": "run_feedback",
                            "type": "bool",
                            "description": "run feedback",
                        }
                    ],
                },
                "template_json": {
                    "type": "subflow",
                    "id": "fan_template",
                    "name": "Fan Template",
                    "in": [{"x": 60, "y": 80, "name": "run_cmd", "wires": []}],
                    "out": [{"x": 380, "y": 110, "name": "run_feedback", "wires": []}],
                    "inputs": 1,
                    "outputs": 1,
                },
                "internal_flow_objects": [],
                "dependency_module_types": [],
                "compile_hints": {
                    "supports_multi_instance": True,
                    "input_count": 1,
                    "output_count": 1,
                },
                "source_info": {
                    "source_flows": ["flows_20240101.json"],
                    "original_subflow_id": "legacy_random_id",
                },
                "similarity_score": 0.87,
                "rank": 1,
            }
        ]
        bundle["metadata"]["retrieved_subflow_count"] = 1
    return bundle


def make_analysis_result() -> dict:
    return {
        "scenario_analysis": {
            "system_type": "AHU",
            "business_goal": "fan control",
            "equipment_object": "supply fan",
            "actuator": "fan",
            "control_strategy": "run control",
            "output_signal": "run command",
            "control_mode": "auto",
            "input_signals": ["run status"],
            "output_signals": ["run command"],
        }
    }


def _message_text(messages) -> str:
    parts = []
    for message in messages:
        content = getattr(message, "content", "")
        if isinstance(content, list):
            content = " ".join(str(item) for item in content)
        parts.append(str(content))
    return "\n".join(parts)


class _BundleAwareStructuredLLM:
    def __init__(self, parent, schema):
        self.parent = parent
        self.schema = schema

    def invoke(self, messages):
        prompt_text = _message_text(messages)
        self.parent.last_prompt_text = prompt_text
        if "Subflow Template Candidates:" in prompt_text and "fan_template" in prompt_text:
            return self.parent.build_plan(
                self.schema,
                "fan_template",
                "Prefer the reusable subflow template.",
            )
        return self.parent.build_plan(
            self.schema,
            "constInput",
            "Fall back to atomic modules.",
        )


class _BundleAwareFakeLLM:
    def __init__(self):
        self.last_prompt_text = ""

    def with_structured_output(self, schema, method=None):  # noqa: ARG002
        return _BundleAwareStructuredLLM(self, schema)

    @staticmethod
    def build_plan(schema, module_type: str, reasoning: str):
        plan_dict = {
            "goal": "bundle-aware planning",
            "nodes": [
                {
                    "logic_id": "selected_module",
                    "module_type": module_type,
                    "parameters": {},
                    "reasoning": reasoning,
                }
            ],
            "connections": [],
        }
        if schema is PlanIR:
            return PlanIR(**plan_dict)
        return schema(**plan_dict)


class Phase2PlanningBundleTests(unittest.TestCase):
    def test_plan_true_path_prefers_subflow_template_when_bundle_exposes_phase2_hints(self):
        fake_llm = _BundleAwareFakeLLM()

        with patch("agents.planning_agent.LLMManager.get_llm", return_value=fake_llm), patch.object(
            config, "DEBUG", False
        ):
            agent = PlanningAgent()
            plan_ir = agent.plan("fan control", make_bundle(include_subflow=True), make_analysis_result())

        self.assertEqual(plan_ir.nodes[0].module_type, "fan_template")
        self.assertIn("System Pattern Hints:", fake_llm.last_prompt_text)
        self.assertIn("Subflow Template Candidates:", fake_llm.last_prompt_text)
        self.assertIn(
            "Prefer reusable subflow templates before falling back to atomic assembly.",
            fake_llm.last_prompt_text,
        )
        self.assertIn(
            "Use system patterns as layout and page hints only, not as hard output schema.",
            fake_llm.last_prompt_text,
        )

    def test_plan_true_path_falls_back_to_atomic_when_bundle_has_no_subflow_templates(self):
        fake_llm = _BundleAwareFakeLLM()

        with patch("agents.planning_agent.LLMManager.get_llm", return_value=fake_llm), patch.object(
            config, "DEBUG", False
        ):
            agent = PlanningAgent()
            plan_ir = agent.plan("fan control", make_bundle(include_subflow=False), make_analysis_result())

        self.assertEqual(plan_ir.nodes[0].module_type, "constInput")
        self.assertIn("System Pattern Hints:", fake_llm.last_prompt_text)
        self.assertNotIn("Subflow Template Candidates:", fake_llm.last_prompt_text)
        self.assertNotIn(
            "Prefer reusable subflow templates before falling back to atomic assembly.",
            fake_llm.last_prompt_text,
        )


if __name__ == "__main__":
    unittest.main()
