from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.poc_phase7_send_parallel import (
    build_graph,
    build_initial_state,
    run_poc,
    subsystem_planning_worker,
)
from utils.phase3_contracts import merge_parallel_conflicts, merge_subsystem_plan_map


class Phase7SendReducerContractTests(unittest.TestCase):
    def test_worker_returns_local_state_update_only(self):
        worker_state = {
            "subsystem_id": "supply_fan_ctrl",
            "dispatch_index": 3,
            "page_id": "ahu_main",
            "subsystem_type": "fan",
            "worker_mode": "plan",
            "subsystem_plan_map": {
                "existing_ctrl": {
                    "subsystem_id": "existing_ctrl",
                    "dispatch_index": 0,
                }
            },
            "parallel_merge_conflicts": [{"type": "existing_conflict"}],
        }
        original_state = copy.deepcopy(worker_state)

        update = subsystem_planning_worker(worker_state)

        self.assertEqual(set(update.keys()), {"subsystem_plan_map"})
        self.assertEqual(list(update["subsystem_plan_map"].keys()), ["supply_fan_ctrl"])
        self.assertEqual(update["subsystem_plan_map"]["supply_fan_ctrl"]["dispatch_index"], 3)
        self.assertEqual(worker_state, original_state)

    def test_parallel_merge_conflicts_is_append_only(self):
        current = [{"type": "first_conflict"}]
        update = [{"type": "second_conflict"}]

        merged = merge_parallel_conflicts(current, update)

        self.assertEqual(merged, [{"type": "first_conflict"}, {"type": "second_conflict"}])
        self.assertEqual(current, [{"type": "first_conflict"}])
        self.assertEqual(update, [{"type": "second_conflict"}])

    def test_merge_subsystem_plan_map_sorts_by_dispatch_index_then_subsystem_id(self):
        merged = merge_subsystem_plan_map(
            {
                "zeta_ctrl": {"subsystem_id": "zeta_ctrl", "dispatch_index": 1},
            },
            {
                "beta_ctrl": {"subsystem_id": "beta_ctrl", "dispatch_index": 0},
                "alpha_ctrl": {"subsystem_id": "alpha_ctrl", "dispatch_index": 1},
            },
        )

        self.assertEqual(list(merged.keys()), ["beta_ctrl", "alpha_ctrl", "zeta_ctrl"])

    def test_send_graph_merges_parallel_workers_with_stable_order(self):
        result = run_poc("stable_order")

        self.assertEqual(list(result["subsystem_plan_map"].keys()), ["beta_ctrl", "alpha_ctrl", "zeta_ctrl"])
        self.assertEqual(result["ordered_subsystem_ids"], ["beta_ctrl", "alpha_ctrl", "zeta_ctrl"])
        self.assertEqual(result["merge_summary"]["stable_sort_rule"], "dispatch_index -> subsystem_id")
        self.assertEqual(result["parallel_merge_conflicts"], [])

    def test_send_graph_collects_parallel_conflicts(self):
        result = build_graph().invoke(build_initial_state("conflict_list"))

        self.assertEqual(result["subsystem_plan_map"], {})
        self.assertEqual(result["merge_summary"]["conflict_count"], 2)
        self.assertEqual(
            {item["subsystem_id"] for item in result["parallel_merge_conflicts"]},
            {"heater_ctrl", "supply_fan_ctrl"},
        )
        self.assertEqual(
            {item["type"] for item in result["parallel_merge_conflicts"]},
            {"parallel_shared_signal_conflict"},
        )

    def test_duplicate_subsystem_id_fails_fast(self):
        with self.assertRaisesRegex(ValueError, "duplicate_subsystem_id:supply_fan_ctrl"):
            run_poc("duplicate_subsystem_id")

    def test_send_poc_isolated_from_formal_workflow_topology(self):
        workflow_text = (PROJECT_ROOT / "workflow.py").read_text(encoding="utf-8")
        workflow_trace_text = (PROJECT_ROOT / "workflow_trace.py").read_text(encoding="utf-8")
        poc_text = (PROJECT_ROOT / "scripts" / "poc_phase7_send_parallel.py").read_text(encoding="utf-8")

        self.assertNotIn("Send(", workflow_text)
        self.assertNotIn("Send(", workflow_trace_text)
        self.assertIn("Send(", poc_text)
        self.assertIn("merge_subsystem_plan_map", poc_text)


if __name__ == "__main__":
    unittest.main()
