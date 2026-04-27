from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import run_phase5_query_suite


class Phase5WorkflowQuerySuiteTests(unittest.TestCase):
    def test_run_suite_writes_summary_and_passes_default_cases(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            suite_summary = run_phase5_query_suite.run_suite(
                output_root=temp_root / "suite_outputs",
                trace_output_root=temp_root / "trace_outputs",
            )

            self.assertTrue(suite_summary["all_passed"])
            self.assertEqual(suite_summary["case_count"], 6)
            self.assertEqual(suite_summary["passed_count"], 6)
            self.assertEqual(suite_summary["failed_count"], 0)
            self.assertTrue(Path(suite_summary["summary_json"]).exists())
            self.assertTrue(Path(suite_summary["summary_md"]).exists())

            results_by_case = {
                item["case_id"]: item
                for item in suite_summary["results"]
            }
            self.assertEqual(
                results_by_case["reject_ambiguous_shared_signal"]["actual"]["repair_reject_category"],
                "ambiguous_shared_signal",
            )
            self.assertEqual(
                results_by_case["reject_budget_exhausted"]["actual"]["reject_reason"],
                "retry_budget_exhausted",
            )
            self.assertGreaterEqual(
                results_by_case["repair_planning_success"]["actual"]["repair_round_count"],
                1,
            )

    def test_multi_round_case_repairs_twice_before_accept(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = run_phase5_query_suite.run_case(
                run_phase5_query_suite.build_multi_round_case(),
                trace_output_root=Path(temp_dir) / "trace_outputs",
            )

        self.assertTrue(result["passed"])
        self.assertEqual(result["actual"]["verification_status"], "passed")
        self.assertEqual(result["actual"]["route_decision"], "accept")
        self.assertGreaterEqual(result["actual"]["repair_round_count"], 2)


if __name__ == "__main__":
    unittest.main()
