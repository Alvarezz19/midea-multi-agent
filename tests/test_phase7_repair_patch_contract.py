from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.repair_agent import RepairAgent
from tests.test_phase4_repair_agent import _assembly_state, _compile_state, _planning_state


class RepairPatchContractTests(unittest.TestCase):
    def test_prepare_repair_patch_returns_planning_plan_without_side_effects(self):
        state = _planning_state()
        agent = RepairAgent()

        plan = agent.prepare_repair_patch(state)

        self.assertEqual(plan["repair_scope"], "planning")
        self.assertEqual(plan["result"], "patched")
        self.assertEqual(plan["reason"], "repair_patch_applied")
        self.assertEqual(plan["target_state_keys"], ["architecture_plan", "decomposition_result"])
        self.assertEqual(plan["retry_counts_by_scope"]["planning"], 1)
        self.assertEqual(plan["operations"][0]["operation"], "bind_shared_signal_owner")
        self.assertEqual(state["architecture_plan"]["shared_signal_registry"][0]["owner_subsystem_id"], "")
        self.assertEqual(state["repair_context"], {})
        self.assertEqual(state["repair_history"], [])

    def test_prepare_repair_patch_returns_assembly_plan(self):
        state = _assembly_state()

        plan = RepairAgent().prepare_repair_patch(state)

        self.assertEqual(plan["repair_scope"], "assembly")
        self.assertEqual(plan["resume_node"], "global_assembly")
        self.assertEqual(plan["operations"][0]["operation"], "remove_invalid_local_edges")
        self.assertEqual(plan["operations"][0]["edge_ids"], ["edge::ghost_remove"])
        self.assertEqual(
            [edge["edge_id"] for edge in state["subsystem_plan_map"]["heater_ctrl"]["edges"]],
            ["edge::valid", "edge::ghost_remove", "edge::ghost_keep"],
        )

    def test_prepare_repair_patch_returns_compile_plan(self):
        state = _compile_state()

        plan = RepairAgent().prepare_repair_patch(state)

        self.assertEqual(plan["repair_scope"], "compile")
        self.assertEqual(plan["resume_node"], "coding")
        self.assertEqual(plan["operations"][0]["operation"], "repair_compile_wires")
        self.assertEqual(plan["operations"][0]["conflict_mode"], "clamp")
        self.assertEqual(state["assembled_graph_ir"]["edges"][0]["to_port"], 2)

    def test_apply_repair_patch_accepts_prepared_compile_plan(self):
        state = _compile_state()
        agent = RepairAgent()
        plan = agent.prepare_repair_patch(state)

        result = agent.apply_repair_patch(state, plan)

        self.assertEqual(result["assembled_graph_ir"]["edges"][0]["to_port"], 0)
        self.assertEqual(result["repair_context"]["patch_instructions"], plan["patch_instructions"])
        self.assertEqual(result["route_decision"]["reason"], "repair_patch_applied")
        self.assertEqual(result["retry_counts_by_scope"]["compile"], 1)


if __name__ == "__main__":
    unittest.main()
