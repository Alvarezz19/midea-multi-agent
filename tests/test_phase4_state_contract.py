from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import workflow
import workflow_trace


class Phase4StateContractTests(unittest.TestCase):
    def test_workflow_state_annotations_include_repair_fields(self):
        expected_fields = {
            "repair_context",
            "repair_history",
            "route_decision",
            "retry_budget",
            "retry_counts_by_scope",
            "hitl_stage",
            "review_request",
            "review_response",
            "review_history",
            "review_enabled",
            "review_required",
            "review_status",
            "review_id",
            "clarification_round",
            "architecture_feedback_patch",
            "enable_hitl_clarification",
            "enable_hitl_architecture_review",
        }

        self.assertTrue(expected_fields.issubset(set(workflow.WorkflowState.__annotations__)))
        self.assertTrue(expected_fields.issubset(set(workflow_trace.WorkflowState.__annotations__)))

    def test_build_initial_state_initializes_repair_defaults(self):
        state = workflow.build_initial_state("为 AHU 生成送风机标准控制")

        self.assertEqual(state["repair_context"], {})
        self.assertEqual(state["repair_history"], [])
        self.assertEqual(state["route_decision"], {})
        self.assertEqual(
            state["retry_budget"],
            {"planning": 2, "assembly": 2, "compile": 2},
        )
        self.assertEqual(
            state["retry_counts_by_scope"],
            {"planning": 0, "assembly": 0, "compile": 0},
        )
        self.assertEqual(state["retry_count"], 0)
        self.assertEqual(state["retry_count"], sum(state["retry_counts_by_scope"].values()))
        self.assertEqual(state["hitl_stage"], "none")
        self.assertEqual(state["review_request"]["stage"], "none")
        self.assertEqual(state["review_response"]["decision"], "")
        self.assertEqual(state["review_history"], [])
        self.assertFalse(state["review_enabled"])
        self.assertFalse(state["review_required"])
        self.assertEqual(state["review_status"], "none")
        self.assertEqual(state["review_id"], "")
        self.assertEqual(state["clarification_round"], 0)
        self.assertEqual(state["architecture_feedback_patch"], {})
        self.assertFalse(state["enable_hitl_clarification"])
        self.assertFalse(state["enable_hitl_architecture_review"])

    def test_run_workflow_passes_recursion_limit_and_preserves_repair_defaults(self):
        captured: dict[str, object] = {}

        class FakeApp:
            def invoke(self, initial_state, config=None):
                captured["initial_state"] = initial_state
                captured["config"] = config
                return initial_state

        class FakeWorkflow:
            def compile(self):
                return FakeApp()

        with patch.object(workflow, "create_workflow", return_value=FakeWorkflow()):
            result = workflow.run_workflow("fan control")

        initial_state = captured["initial_state"]
        invoke_config = captured["config"]

        self.assertEqual(invoke_config["recursion_limit"], workflow.PHASE4_RECURSION_LIMIT)
        self.assertEqual(initial_state["route_decision"], {})
        self.assertEqual(initial_state["retry_count"], sum(initial_state["retry_counts_by_scope"].values()))
        self.assertEqual(result["repair_history"], [])

    def test_trace_run_workflow_passes_recursion_limit_and_keeps_repair_defaults(self):
        captured: dict[str, object] = {}

        class FakeApp:
            def invoke(self, initial_state, config=None):
                captured["initial_state"] = initial_state
                captured["config"] = config
                return initial_state

        class FakeWorkflow:
            def compile(self):
                return FakeApp()

        with patch.object(workflow_trace, "create_workflow", return_value=FakeWorkflow()), patch.object(
            workflow_trace,
            "_save_workflow_trace",
            return_value={"trace_dir": "mock-trace"},
        ):
            result = workflow_trace.run_workflow("fan control")

        initial_state = captured["initial_state"]
        invoke_config = captured["config"]

        self.assertEqual(invoke_config["recursion_limit"], workflow.PHASE4_RECURSION_LIMIT)
        self.assertEqual(initial_state["repair_context"], {})
        self.assertEqual(initial_state["retry_count"], sum(initial_state["retry_counts_by_scope"].values()))
        self.assertEqual(result["final_output"]["workflow_trace"]["trace_dir"], "mock-trace")


if __name__ == "__main__":
    unittest.main()
