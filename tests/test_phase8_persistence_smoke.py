from __future__ import annotations

import sys
import unittest
from pathlib import Path

from langgraph.types import Command


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_phase8_hitl_smoke import (
    build_resume_payload,
    build_smoke_graph,
    build_smoke_initial_state,
)
from utils.workflow_runtime import build_configurable_thread


class Phase8PersistenceSmokeTests(unittest.TestCase):
    def test_clarification_smoke_supports_pause_resume_and_state_history(self):
        graph = build_smoke_graph("clarification")
        config = {"configurable": build_configurable_thread("phase8-smoke-clarification")}
        first = graph.invoke(build_smoke_initial_state("clarification"), config)

        self.assertIn("__interrupt__", first)
        paused = graph.get_state(config)
        self.assertEqual(paused.values["review_request"]["stage"], "clarification_review")
        self.assertEqual(tuple(paused.next), ("clarification_review",))

        resumed = graph.invoke(
            Command(resume=build_resume_payload("clarification", "clarify", paused.values["review_id"])),
            config,
        )

        self.assertEqual(resumed["clarification_round"], 1)
        self.assertEqual(resumed["requirement_spec"]["system_type"], "AHU")
        self.assertEqual(resumed["route_decision"]["decision"], "accept")
        self.assertGreaterEqual(len(list(graph.get_state_history(config))), 3)

    def test_architecture_smoke_feedback_replans_then_requires_same_thread_to_continue(self):
        graph = build_smoke_graph("architecture")
        config = {"configurable": build_configurable_thread("phase8-smoke-architecture")}
        first = graph.invoke(build_smoke_initial_state("architecture"), config)

        self.assertIn("__interrupt__", first)
        paused = graph.get_state(config)
        self.assertEqual(paused.values["review_request"]["stage"], "architecture_review")

        second = graph.invoke(
            Command(resume=build_resume_payload("architecture", "feedback", paused.values["review_id"])),
            config,
        )

        self.assertIn("__interrupt__", second)
        replanned = graph.get_state(config)
        self.assertEqual([page["label"] for page in replanned.values["architecture_plan"]["pages"]], ["控制", "总览"])
        self.assertEqual(replanned.values["architecture_feedback_patch"]["decision"], "feedback")

        final = graph.invoke(
            Command(resume=build_resume_payload("architecture", "approve", replanned.values["review_id"])),
            config,
        )

        self.assertEqual(final["route_decision"]["decision"], "accept")
        self.assertEqual(final["subsystem_plan_map"]["supply_fan_ctrl"]["status"], "planned")


if __name__ == "__main__":
    unittest.main()
