from __future__ import annotations

import sys
import unittest
from pathlib import Path

from langgraph.graph import StateGraph


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.repair_router import RepairRouter
import workflow


def make_state(
    *,
    status: str = "retryable_error",
    repair_scope: str = "planning",
    issues: list[dict] | None = None,
    retry_budget: dict | None = None,
    retry_counts_by_scope: dict | None = None,
    retry_count: int | None = None,
) -> dict:
    state = workflow.build_initial_state("为 AHU 生成送风机标准控制")
    state["verification_report"] = {
        "status": status,
        "repair_scope": repair_scope,
        "issues": issues or [],
        "warnings": [],
        "metrics": {},
    }
    if retry_budget is not None:
        state["retry_budget"] = retry_budget
    if retry_counts_by_scope is not None:
        state["retry_counts_by_scope"] = retry_counts_by_scope
    if retry_count is not None:
        state["retry_count"] = retry_count
    return state


class RepairRouterTests(unittest.TestCase):
    def test_router_accepts_passed_verification(self):
        state = make_state(status="passed", repair_scope="none")

        result = RepairRouter()(state)

        self.assertEqual(result["route_decision"]["decision"], "accept")
        self.assertEqual(result["route_decision"]["next_node"], "END")
        self.assertEqual(result["route_decision"]["reason"], "verification_passed")
        self.assertEqual(result["route_decision"]["issue_ids"], [])
        self.assertFalse(result["route_decision"]["retry_exhausted"])

    def test_router_rejects_invalid_scope(self):
        state = make_state(
            repair_scope="fatal",
            issues=[{"issue_id": "IR-001"}, {"issue_id": "CP-002"}],
        )

        result = RepairRouter()(state)

        self.assertEqual(result["route_decision"]["decision"], "reject")
        self.assertEqual(result["route_decision"]["next_node"], "END")
        self.assertEqual(result["route_decision"]["reason"], "unsupported_repair_scope")
        self.assertEqual(result["route_decision"]["issue_ids"], ["IR-001", "CP-002"])
        self.assertEqual(result["route_decision"]["retry_count_for_scope"], 0)
        self.assertEqual(result["route_decision"]["retry_budget_for_scope"], 0)

    def test_router_routes_supported_scope_when_budget_is_available(self):
        state = make_state(
            repair_scope="assembly",
            issues=[{"issue_id": "IR-003"}],
            retry_counts_by_scope={"planning": 2, "assembly": 1, "compile": 0},
        )

        result = RepairRouter()(state)

        self.assertEqual(result["route_decision"]["decision"], "assembly_repair")
        self.assertEqual(result["route_decision"]["next_node"], "repair_agent")
        self.assertEqual(result["route_decision"]["reason"], "assembly_retry_allowed")
        self.assertEqual(result["route_decision"]["issue_ids"], ["IR-003"])
        self.assertEqual(result["route_decision"]["retry_count_for_scope"], 1)
        self.assertEqual(result["route_decision"]["retry_budget_for_scope"], 2)

    def test_router_rejects_when_scope_budget_is_exhausted(self):
        state = make_state(
            repair_scope="compile",
            retry_counts_by_scope={"planning": 0, "assembly": 1, "compile": 2},
        )

        result = RepairRouter()(state)

        self.assertEqual(result["route_decision"]["decision"], "reject")
        self.assertEqual(result["route_decision"]["reason"], "retry_budget_exhausted")
        self.assertTrue(result["route_decision"]["retry_exhausted"])
        self.assertEqual(result["route_decision"]["retry_count_for_scope"], 2)
        self.assertEqual(result["route_decision"]["retry_budget_for_scope"], 2)

    def test_router_uses_scope_counts_instead_of_total_retry_count(self):
        state = make_state(
            repair_scope="planning",
            retry_counts_by_scope={"planning": 0, "assembly": 2, "compile": 2},
            retry_count=99,
        )

        result = RepairRouter()(state)

        self.assertEqual(result["route_decision"]["decision"], "planning_repair")
        self.assertEqual(result["route_decision"]["reason"], "planning_retry_allowed")
        self.assertEqual(result["retry_count"], 4)
        self.assertEqual(result["retry_count"], sum(result["retry_counts_by_scope"].values()))

    def test_router_does_not_add_business_branch_for_ambiguous_shared_signal(self):
        state = make_state(
            repair_scope="planning",
            issues=[
                {
                    "issue_id": "IR-AMB-001",
                    "scope": "planning",
                    "rule_id": "ir.unresolved.ambiguous_shared_signal",
                }
            ],
        )

        result = RepairRouter()(state)

        self.assertEqual(result["route_decision"]["decision"], "planning_repair")
        self.assertEqual(result["route_decision"]["reason"], "planning_retry_allowed")
        self.assertEqual(result["route_decision"]["next_node"], "repair_agent")

    def test_phase4_topology_helper_can_register_repair_loop(self):
        def _noop(state):
            return state

        nodes = {node_name: _noop for node_name in workflow.PHASE3_NODE_ORDER}
        nodes["repair_router"] = _noop
        nodes["repair_agent"] = _noop

        graph = workflow.populate_phase4_workflow(
            StateGraph(workflow.WorkflowState),
            nodes,
            enable_repair_loop=True,
        )

        self.assertIsNotNone(graph.compile())


if __name__ == "__main__":
    unittest.main()
