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


class Phase7RuntimeContractTests(unittest.TestCase):
    def test_workflow_old_call_still_works(self):
        captured: dict[str, object] = {}

        class FakeApp:
            def invoke(self, initial_state, config=None):
                captured["initial_state"] = initial_state
                captured["config"] = config
                return initial_state

        class FakeWorkflow:
            def compile(self, **kwargs):
                captured["compile_kwargs"] = kwargs
                return FakeApp()

        with patch.object(workflow, "create_workflow", return_value=FakeWorkflow()):
            result = workflow.run_workflow("fan control")

        self.assertEqual(captured["compile_kwargs"], {})
        self.assertEqual(captured["config"]["metadata"]["user_query"], "fan control")
        self.assertEqual(captured["config"]["metadata"]["persistence_enabled"], False)
        self.assertNotIn("configurable", captured["config"])
        self.assertEqual(result["user_query"], "fan control")

    def test_workflow_thread_id_without_checkpointer_stays_in_metadata_only(self):
        captured: dict[str, object] = {}

        class FakeApp:
            def invoke(self, initial_state, config=None):
                captured["config"] = config
                return initial_state

        class FakeWorkflow:
            def compile(self, **kwargs):
                captured["compile_kwargs"] = kwargs
                return FakeApp()

        with patch.object(workflow, "create_workflow", return_value=FakeWorkflow()):
            workflow.run_workflow("fan control", thread_id="phase7-thread")

        self.assertEqual(captured["compile_kwargs"], {})
        self.assertEqual(captured["config"]["metadata"]["thread_id"], "phase7-thread")
        self.assertFalse(captured["config"]["metadata"]["persistence_enabled"])
        self.assertNotIn("configurable", captured["config"])

    def test_workflow_checkpointer_requires_thread_id_and_propagates_to_configurable(self):
        captured: dict[str, object] = {}
        fake_checkpointer = object()

        class FakeApp:
            def invoke(self, initial_state, config=None):
                captured["config"] = config
                return initial_state

        class FakeWorkflow:
            def compile(self, **kwargs):
                captured["compile_kwargs"] = kwargs
                return FakeApp()

        with patch.object(workflow, "create_workflow", return_value=FakeWorkflow()):
            workflow.run_workflow(
                "fan control",
                thread_id="phase7-thread",
                checkpointer=fake_checkpointer,
            )

        self.assertIs(captured["compile_kwargs"]["checkpointer"], fake_checkpointer)
        self.assertEqual(
            captured["config"]["configurable"],
            {"thread_id": "phase7-thread"},
        )
        self.assertTrue(captured["config"]["metadata"]["persistence_enabled"])

        with patch.object(workflow, "create_workflow", return_value=FakeWorkflow()):
            with self.assertRaises(ValueError):
                workflow.run_workflow("fan control", checkpointer=fake_checkpointer)

    def test_trace_workflow_runtime_config_includes_thread_id_and_attempt_id(self):
        captured: dict[str, object] = {}

        class FakeApp:
            def invoke(self, initial_state, config=None):
                captured["config"] = config
                return initial_state

        class FakeWorkflow:
            def compile(self, **kwargs):
                captured["compile_kwargs"] = kwargs
                return FakeApp()

        with patch.object(workflow_trace, "create_workflow", return_value=FakeWorkflow()), patch.object(
            workflow_trace,
            "_save_workflow_trace",
            return_value={"trace_dir": "mock-trace", "thread_id": "phase7-thread", "attempt_id": "attempt-1"},
        ):
            result = workflow_trace.run_workflow("fan control", thread_id="phase7-thread")

        self.assertEqual(captured["compile_kwargs"], {})
        self.assertEqual(captured["config"]["metadata"]["thread_id"], "phase7-thread")
        self.assertIn("attempt_id", captured["config"]["metadata"])
        self.assertEqual(result["final_output"]["workflow_trace"]["thread_id"], "phase7-thread")


if __name__ == "__main__":
    unittest.main()
