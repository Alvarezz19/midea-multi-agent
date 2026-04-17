from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class Phase7BaselineContractTests(unittest.TestCase):
    def test_phase6_retained_green_baselines_exist(self):
        suite_marker_path = PROJECT_ROOT / "outputs" / "phase6_real_query_suite" / "_retained" / "latest_green_run.json"
        retrieval_marker_path = PROJECT_ROOT / "outputs" / "phase6_retrieval_eval" / "_retained" / "latest_green_run.json"

        suite_marker = json.loads(suite_marker_path.read_text(encoding="utf-8"))
        retrieval_marker = json.loads(retrieval_marker_path.read_text(encoding="utf-8"))

        self.assertTrue(suite_marker["all_passed"])
        self.assertEqual(suite_marker["case_count"], 12)
        self.assertTrue(Path(suite_marker["run_dir"]).exists())

        self.assertTrue(retrieval_marker["all_passed"])
        self.assertEqual(retrieval_marker["case_count"], 12)
        self.assertTrue(Path(retrieval_marker["run_dir"]).exists())

    def test_mainline_topology_has_not_switched_to_send(self):
        workflow_text = (PROJECT_ROOT / "workflow.py").read_text(encoding="utf-8")
        workflow_trace_text = (PROJECT_ROOT / "workflow_trace.py").read_text(encoding="utf-8")

        self.assertIn("PHASE3_NODE_ORDER", workflow_text)
        self.assertIn('"subsystem_planning"', workflow_text)
        self.assertIn("populate_phase4_workflow", workflow_trace_text)
        self.assertNotIn("subsystem_dispatcher", workflow_text)
        self.assertNotIn("Send(", workflow_text)
        self.assertNotIn("Send(", workflow_trace_text)

    def test_phase6_handoff_doc_freezes_trace_evidence_and_flake_conclusion(self):
        handoff_path = PROJECT_ROOT / "AHU程序" / "第六阶段当前状态交接.md"
        text = handoff_path.read_text(encoding="utf-8")

        expected_paths = [
            "workflow_trace_20260417_103540_891655",
            "workflow_trace_20260417_103600_366901",
            "workflow_trace_20260417_103620_265872",
        ]
        for path_token in expected_paths:
            with self.subTest(path_token=path_token):
                self.assertIn(path_token, text)

        self.assertIn("截至 2026-04-17 的最新结论：未复现", text)


if __name__ == "__main__":
    unittest.main()
