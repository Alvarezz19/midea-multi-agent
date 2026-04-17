from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import workflow_trace


class Phase7TraceIndexContractTests(unittest.TestCase):
    def test_trace_output_contains_thread_and_attempt_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            trace_root = Path(temp_dir)

            class FakeApp:
                def invoke(self, initial_state, config=None):
                    return initial_state

            class FakeWorkflow:
                def compile(self, **kwargs):
                    return FakeApp()

            with patch.object(workflow_trace, "TRACE_OUTPUT_ROOT", str(trace_root)), patch.object(
                workflow_trace,
                "create_workflow",
                return_value=FakeWorkflow(),
            ):
                result = workflow_trace.run_workflow("fan control", thread_id="phase7-thread")

            trace_info = result["final_output"]["workflow_trace"]
            self.assertEqual(trace_info["thread_id"], "phase7-thread")
            self.assertTrue(trace_info["attempt_id"])
            self.assertTrue(Path(trace_info["trace_dir"]).exists())
            self.assertTrue(Path(trace_info["summary_json"]).exists())
            self.assertTrue(Path(trace_info["summary_md"]).exists())
            self.assertTrue(Path(trace_info["final_state_json"]).exists())
            self.assertTrue(Path(trace_info["thread_index_json"]).exists())
            self.assertTrue(Path(trace_info["attempt_index_json"]).exists())

            summary = json.loads(Path(trace_info["summary_json"]).read_text(encoding="utf-8"))
            self.assertEqual(summary["thread_id"], "phase7-thread")
            self.assertEqual(summary["attempt_id"], trace_info["attempt_id"])

            thread_index = json.loads(Path(trace_info["thread_index_json"]).read_text(encoding="utf-8"))
            self.assertEqual(thread_index["thread_id"], "phase7-thread")
            self.assertEqual(len(thread_index["attempts"]), 1)
            self.assertEqual(thread_index["attempts"][0]["attempt_id"], trace_info["attempt_id"])

    def test_same_thread_id_multiple_runs_get_distinct_attempt_ids(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            trace_root = Path(temp_dir)

            class FakeApp:
                def invoke(self, initial_state, config=None):
                    return initial_state

            class FakeWorkflow:
                def compile(self, **kwargs):
                    return FakeApp()

            with patch.object(workflow_trace, "TRACE_OUTPUT_ROOT", str(trace_root)), patch.object(
                workflow_trace,
                "create_workflow",
                return_value=FakeWorkflow(),
            ):
                first = workflow_trace.run_workflow("fan control", thread_id="phase7-thread")
                second = workflow_trace.run_workflow("fan control", thread_id="phase7-thread")

            first_trace = first["final_output"]["workflow_trace"]
            second_trace = second["final_output"]["workflow_trace"]
            self.assertNotEqual(first_trace["attempt_id"], second_trace["attempt_id"])

            thread_index = json.loads(Path(second_trace["thread_index_json"]).read_text(encoding="utf-8"))
            self.assertEqual(len(thread_index["attempts"]), 2)
            self.assertEqual(
                {item["attempt_id"] for item in thread_index["attempts"]},
                {first_trace["attempt_id"], second_trace["attempt_id"]},
            )

    def test_trace_without_thread_id_preserves_timestamp_dir_compatibility(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            trace_root = Path(temp_dir)

            class FakeApp:
                def invoke(self, initial_state, config=None):
                    return initial_state

            class FakeWorkflow:
                def compile(self, **kwargs):
                    return FakeApp()

            with patch.object(workflow_trace, "TRACE_OUTPUT_ROOT", str(trace_root)), patch.object(
                workflow_trace,
                "create_workflow",
                return_value=FakeWorkflow(),
            ):
                result = workflow_trace.run_workflow("fan control")

            trace_info = result["final_output"]["workflow_trace"]
            self.assertEqual(trace_info["thread_id"], "")
            self.assertTrue(trace_info["attempt_id"])
            self.assertTrue(Path(trace_info["trace_dir"]).name.startswith("workflow_trace_"))
            self.assertNotIn("thread_index_json", trace_info)
            self.assertNotIn("attempt_index_json", trace_info)


if __name__ == "__main__":
    unittest.main()
