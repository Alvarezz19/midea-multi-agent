from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
import workflow
import workflow_trace
from utils.retrieval_bundle_utils import build_legacy_retrieval_context


def make_requirement_spec() -> dict:
    return {
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
                "imports": ["schedule_enable"],
                "exports": ["supply_fan_available_flag"],
            }
        ],
        "signals": {"inputs": [], "outputs": [], "software_points": [], "alarm_points": []},
        "required_pages": ["IO/通讯", "控制", "定时"],
        "global_modes": ["schedule_enable"],
        "ambiguities": [],
        "assumptions": [],
        "acceptance_criteria": [],
        "confidence": 0.8,
        "warnings": [],
    }


def make_bundle() -> dict:
    return {
        "atomic_modules": [
            {
                "module_type": "constInput",
                "name": "Constant Input",
                "category": "logic/basic",
                "description": "Provide a constant numeric value.",
                "parameters_schema": {"fixedValue": {"type": "number"}},
                "ports_definition": {"inputs": [], "outputs": [{"index": 0, "label": "out"}]},
                "template_json": {"type": "constInput", "inputs": 0, "outputs": 1},
            }
        ],
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
                    "inputs": [{"index": 0, "label": "schedule_enable"}],
                    "outputs": [{"index": 0, "label": "supply_fan_available_flag"}],
                },
                "template_json": {
                    "type": "subflow",
                    "id": "fan_template",
                    "name": "送风机标准控制",
                    "in": [{"x": 60, "y": 80, "name": "schedule_enable", "wires": []}],
                    "out": [{"x": 380, "y": 110, "name": "supply_fan_available_flag", "wires": []}],
                    "inputs": 1,
                    "outputs": 1,
                },
                "compile_hints": {"input_count": 1, "output_count": 1},
            }
        ],
        "system_patterns": [
            {
                "pattern_id": "ahu_test_pattern",
                "required_pages": [
                    {"page_key": "control", "label": "控制", "kind": "control"},
                    {"page_key": "io_comm", "label": "IO/通讯", "kind": "io"},
                ],
                "optional_pages": [{"page_key": "timing", "label": "定时", "kind": "timing"}],
            }
        ],
        "style_guides": [],
        "metadata": {"selected_case_pattern_id": "ahu_test_pattern"},
    }


class StubAnalysis:
    def __call__(self, state):
        state["analysis_result"] = {
            "scenario_analysis": {
                "summary": "送风机控制",
                "system_type": "AHU",
                "input_signals": ["schedule_enable"],
                "output_signals": ["supply_fan_available_flag"],
            }
        }
        state["requirement_spec"] = make_requirement_spec()
        state["current_step"] = "analysis_completed"
        return state


class StubRetrieval:
    def __call__(self, state):
        bundle = make_bundle()
        state["retrieval_bundle"] = bundle
        state["retrieval_context"] = build_legacy_retrieval_context(bundle)
        state["current_step"] = "retrieval_completed"
        return state


class Phase3WorkflowTests(unittest.TestCase):
    def test_workflow_runs_phase3_linear_chain(self):
        with patch.object(config, "DEBUG", False), \
             patch.object(workflow, "AnalysisAgent", StubAnalysis), \
             patch.object(workflow, "RetrievalAgent", StubRetrieval):
            result = workflow.run_workflow("送风机控制")

        self.assertIn("decomposition_result", result)
        self.assertIn("architecture_plan", result)
        self.assertIn("subsystem_plan_map", result)
        self.assertIn("assembled_graph_ir", result)
        self.assertTrue(result["execution_plan"]["nodes"])
        self.assertEqual(result["verification_report"]["status"], "passed")
        self.assertEqual(result["final_output"]["verification_report"]["status"], "passed")

    def test_workflow_trace_records_phase3_fields(self):
        with patch.object(config, "DEBUG", False), \
             patch.object(workflow_trace, "AnalysisAgent", StubAnalysis), \
             patch.object(workflow_trace, "RetrievalAgent", StubRetrieval), \
             patch.object(workflow_trace, "_save_workflow_trace", return_value={"trace_dir": "mock-trace"}):
            result = workflow_trace.run_workflow("送风机控制")

        self.assertEqual(result["verification_report"]["status"], "passed")
        self.assertEqual(result["final_output"]["workflow_trace"]["trace_dir"], "mock-trace")
        self.assertIn("architecture_plan", result)
        self.assertIn("subsystem_plan_map", result)


if __name__ == "__main__":
    unittest.main()
