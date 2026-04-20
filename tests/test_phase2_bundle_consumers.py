from __future__ import annotations

import sys
import unittest
from unittest.mock import patch
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
from agents.assembly_agent import AssemblyAgent
from agents.coding_agent import CodingAgent
from agents.planning_agent import PlanIR, PlanNode, PlanningAgent


class _DummyPrompt:
    def __init__(self):
        self.last_kwargs = None

    def format_messages(self, **kwargs):
        self.last_kwargs = kwargs
        return [{"role": "system", "content": "dummy"}]


def make_bundle():
    return {
        "atomic_modules": [
            {
                "module_type": "constInput",
                "name": "Constant Input",
                "category": "logic/basic",
                "description": "Provide a constant numeric value.",
                "parameters_schema": {"fixedValue": {"type": "number", "description": "constant value"}},
                "ports_definition": {
                    "inputs": [],
                    "outputs": [{"index": 0, "label": "out", "type": "number", "description": "output"}],
                },
                "template_json": {"type": "constInput", "inputs": 0, "outputs": 1},
                "similarity_score": 0.91,
                "rank": 1,
            }
        ],
        "subflow_templates": [
            {
                "module_type": "fan_template",
                "asset_type": "subflow_template",
                "template_id": "fan_template",
                "definition_id": "fan_template",
                "template_name": "Fan Template",
                "name": "Fan Template",
                "category": "AHU?????/fan_control",
                "description": "Reusable fan control subflow.",
                "parameters_schema": {},
                "ports_definition": {
                    "inputs": [
                        {"index": 0, "label": "run_cmd", "type": "bool", "description": "run command"},
                        {"index": 1, "label": "fault_reset", "type": "bool", "description": "fault reset"},
                    ],
                    "outputs": [
                        {"index": 0, "label": "run_feedback", "type": "bool", "description": "run feedback"},
                    ],
                },
                "template_json": {
                    "type": "subflow",
                    "id": "fan_template",
                    "name": "Fan Template",
                    "in": [
                        {"x": 60, "y": 80, "name": "run_cmd", "wires": []},
                        {"x": 60, "y": 140, "name": "fault_reset", "wires": []},
                    ],
                    "out": [
                        {"x": 380, "y": 110, "name": "run_feedback", "wires": []},
                    ],
                    "inputs": 2,
                    "outputs": 1,
                },
                "internal_flow_objects": [],
                "dependency_module_types": [],
                "compile_hints": {"supports_multi_instance": True, "input_count": 2, "output_count": 1},
                "source_info": {"source_flows": ["flows_20240101.json"], "original_subflow_id": "legacy_random_id"},
                "similarity_score": 0.87,
                "rank": 1,
            }
        ],
        "system_patterns": [
            {
                "pattern_id": "ahu_ctrl__v1",
                "pattern_name": "AHU control skeleton",
                "system_type": "AHU",
                "required_pages": [{"page_key": "control", "label": "??", "kind": "control"}],
                "optional_pages": [{"page_key": "timing", "label": "??", "kind": "timing"}],
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
            "retrieved_subflow_count": 1,
            "retrieved_pattern_count": 1,
            "avg_atomic_score": 0.91,
            "query_bundle_version": "phase2-v1",
        },
    }


def make_execution_plan():
    return {
        "goal": "Reuse the fan template",
        "nodes": [
            {
                "logic_id": "fan_control",
                "module_type": "fan_template",
                "parameters": {"name": "Supply Fan"},
                "reasoning": "Reuse the Phase 2 subflow template.",
            }
        ],
        "connections": [],
    }


class Phase2BundleConsumerTests(unittest.TestCase):
    def test_planning_agent_plan_accepts_subflow_module_type_from_bundle(self):
        agent = PlanningAgent.__new__(PlanningAgent)
        agent.planning_prompt = _DummyPrompt()
        agent._format_analysis_context = lambda analysis_result: "analysis"
        agent._generate_plan = lambda messages: PlanIR(
            goal="Reuse the fan template",
            nodes=[
                PlanNode(
                    logic_id="fan_control",
                    module_type="fan_template",
                    parameters={},
                    reasoning="Prefer the reusable template.",
                )
            ],
            connections=[],
        )

        with patch.object(config, "DEBUG", False):
            plan_ir = agent.plan("fan control", make_bundle(), analysis_result={})

        self.assertEqual(plan_ir.nodes[0].module_type, "fan_template")
        self.assertEqual(agent._available_module_types, {"constInput", "fan_template"})
        self.assertIn("Subflow Template Candidates:", agent.planning_prompt.last_kwargs["slim_context"])
        self.assertIn("System Pattern Hints:", agent.planning_prompt.last_kwargs["slim_context"])

    def test_planning_agent_call_prefers_bundle(self):
        agent = PlanningAgent.__new__(PlanningAgent)
        captured = {}

        def fake_plan(user_query, bundle_or_context, analysis_result=None):
            captured["user_query"] = user_query
            captured["bundle_or_context"] = bundle_or_context
            captured["analysis_result"] = analysis_result
            return PlanIR(goal="ok", nodes=[], connections=[])

        agent.plan = fake_plan
        bundle = make_bundle()
        legacy_context = {"query": "legacy", "relevant_nodes": [{"module_type": "legacy_only"}]}
        state = {
            "user_query": "fan control",
            "retrieval_bundle": bundle,
            "retrieval_context": legacy_context,
            "analysis_result": {"scenario_analysis": {"system_type": "AHU"}},
        }

        result = agent.__call__(state)

        self.assertIs(captured["bundle_or_context"], bundle)
        self.assertEqual(captured["user_query"], "fan control")
        self.assertEqual(result["execution_plan"]["goal"], "ok")
        self.assertEqual(result["current_step"], "planning_completed")

    def test_assembly_agent_call_uses_bundle_for_subflow_templates(self):
        agent = AssemblyAgent()
        state = {
            "execution_plan": make_execution_plan(),
            "retrieval_bundle": make_bundle(),
            "retrieval_context": {"query": "legacy", "relevant_nodes": []},
        }

        result = agent.__call__(state)
        assembled = result["assembled_graph_ir"]

        self.assertEqual(result["current_step"], "assembly_completed")
        self.assertEqual(len(assembled["subflow_definitions"]), 1)
        self.assertEqual(assembled["subflow_definitions"][0]["template_id"], "fan_template")
        self.assertEqual(assembled["subflow_definitions"][0]["definition_id"], "fan_template")
        self.assertEqual(assembled["node_instances"][0]["template_id"], "fan_template")
        self.assertEqual(assembled["unresolved_items"], [])

    def test_coding_agent_call_compiles_bundle_backed_subflow(self):
        bundle = make_bundle()
        assembled = AssemblyAgent().assemble(make_execution_plan(), bundle)

        agent = CodingAgent()
        state = {
            "assembled_graph_ir": assembled,
            "retrieval_bundle": bundle,
        }

        result = agent.__call__(state)
        artifact = result["compiled_artifact"]
        artifact_recompiled = agent.compile_graph(assembled, bundle)
        flow_types = [obj.get("type") for obj in artifact["flow_objects"]]

        self.assertEqual(result["current_step"], "coding_completed")
        self.assertIn("tab", flow_types)
        self.assertIn("subflow", flow_types)
        self.assertTrue(any(obj_type.startswith("subflow:") for obj_type in flow_types if isinstance(obj_type, str)))
        self.assertEqual(artifact["compile_report"]["page_count"], 1)
        self.assertEqual(artifact["compile_report"]["subflow_count"], 1)
        self.assertEqual(artifact["compile_report"]["node_count"], 1)
        self.assertEqual(artifact["id_map"], artifact_recompiled["id_map"])
        self.assertEqual(artifact["json_text"], artifact_recompiled["json_text"])
        self.assertIn('"type": "subflow"', artifact["json_text"])
        self.assertNotIn("generated_code", result)


if __name__ == "__main__":
    unittest.main()
