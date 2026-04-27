from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import workflow
import workflow_trace


def _summary_for(final_state: dict) -> dict:
    return workflow_trace._build_trace_summary(
        user_query=final_state.get("user_query", "phase4 trace"),
        node_io_records=[
            {"node_name": "verification", "status": "success", "output": {}},
            {"node_name": "repair_router", "status": "success", "output": {}},
        ],
        final_state=final_state,
        total_elapsed_seconds=1.23,
    )


class Phase4TraceSummaryTests(unittest.TestCase):
    def test_summary_distinguishes_first_pass_accept(self):
        state = workflow.build_initial_state("first pass")
        state["verification_report"] = {
            "status": "passed",
            "repair_scope": "none",
            "issue_summary": "结构校验通过。",
            "issues": [],
            "warnings": [],
            "metrics": {},
        }
        state["route_decision"] = {
            "decision": "accept",
            "repair_scope": "none",
            "next_node": "END",
            "reason": "verification_passed",
            "issue_ids": [],
            "retry_exhausted": False,
            "retry_count_for_scope": 0,
            "retry_budget_for_scope": 2,
        }

        summary = _summary_for(state)

        self.assertEqual(summary["repair_round_count"], 0)
        self.assertEqual(summary["repair_scopes_seen"], [])
        self.assertEqual(summary["final_route_decision"], "accept")
        self.assertFalse(summary["retry_exhausted"])
        self.assertEqual(summary["retry_counts_by_scope"], {"planning": 0, "assembly": 0, "compile": 0})
        self.assertEqual(summary["last_repair_issue_ids"], [])
        self.assertEqual(summary["last_repair_actions"], [])
        self.assertEqual(summary["reject_reason"], "")
        self.assertEqual(summary["planning_unresolved_by_type"], {})
        self.assertEqual(summary["ambiguous_signal_count"], 0)
        self.assertEqual(summary["repair_reject_category"], "")

    def test_summary_distinguishes_repair_then_accept(self):
        state = workflow.build_initial_state("repair then pass")
        state["verification_report"] = {
            "status": "passed",
            "repair_scope": "none",
            "issue_summary": "修复后通过。",
            "issues": [],
            "warnings": [],
            "metrics": {},
        }
        state["repair_history"] = [
            {
                "round": 1,
                "scope": "planning",
                "issue_ids": ["IR-001"],
                "target_state_keys": ["architecture_plan", "decomposition_result"],
                "actions": ["将共享信号 supply_fan_available_flag 的 owner_subsystem_id 收敛为 supply_fan_ctrl。"],
                "result": "patched",
                "next_node": "subsystem_planning",
            }
        ]
        state["route_decision"] = {
            "decision": "accept",
            "repair_scope": "none",
            "next_node": "END",
            "reason": "verification_passed",
            "issue_ids": [],
            "retry_exhausted": False,
            "retry_count_for_scope": 0,
            "retry_budget_for_scope": 2,
        }
        state["retry_counts_by_scope"] = {"planning": 1, "assembly": 0, "compile": 0}
        state["retry_count"] = 1

        summary = _summary_for(state)

        self.assertEqual(summary["repair_round_count"], 1)
        self.assertEqual(summary["repair_scopes_seen"], ["planning"])
        self.assertEqual(summary["final_route_decision"], "accept")
        self.assertFalse(summary["retry_exhausted"])
        self.assertEqual(summary["retry_counts_by_scope"]["planning"], 1)
        self.assertEqual(summary["last_repair_issue_ids"], ["IR-001"])
        self.assertEqual(
            summary["last_repair_actions"],
            ["将共享信号 supply_fan_available_flag 的 owner_subsystem_id 收敛为 supply_fan_ctrl。"],
        )
        self.assertEqual(summary["reject_reason"], "")
        self.assertEqual(summary["planning_unresolved_by_type"], {})
        self.assertEqual(summary["ambiguous_signal_count"], 0)
        self.assertEqual(summary["repair_reject_category"], "")

    def test_summary_distinguishes_budget_exhausted_reject(self):
        state = workflow.build_initial_state("budget exhausted")
        state["verification_report"] = {
            "status": "retryable_error",
            "repair_scope": "compile",
            "issue_summary": "达到 compile scope 重试上限。",
            "issues": [
                {
                    "issue_id": "CP-001",
                    "scope": "compile",
                    "target_id": "src1",
                    "rule_id": "compile.wire.port.range",
                    "message": "wire 引用了越界端口: dst1[2] / inputs=1",
                }
            ],
            "warnings": [],
            "metrics": {"invalid_port_refs": 1},
        }
        state["route_decision"] = {
            "decision": "reject",
            "repair_scope": "compile",
            "next_node": "END",
            "reason": "retry_budget_exhausted",
            "issue_ids": ["CP-001"],
            "retry_exhausted": True,
            "retry_count_for_scope": 2,
            "retry_budget_for_scope": 2,
        }
        state["retry_counts_by_scope"] = {"planning": 0, "assembly": 0, "compile": 2}
        state["retry_count"] = 2

        summary = _summary_for(state)

        self.assertEqual(summary["repair_round_count"], 0)
        self.assertEqual(summary["repair_scopes_seen"], ["compile"])
        self.assertEqual(summary["final_route_decision"], "reject")
        self.assertTrue(summary["retry_exhausted"])
        self.assertEqual(summary["retry_counts_by_scope"], {"planning": 0, "assembly": 0, "compile": 2})
        self.assertEqual(summary["last_repair_issue_ids"], ["CP-001"])
        self.assertEqual(summary["last_repair_actions"], [])
        self.assertEqual(summary["reject_reason"], "retry_budget_exhausted")
        self.assertEqual(summary["planning_unresolved_by_type"], {})
        self.assertEqual(summary["ambiguous_signal_count"], 0)
        self.assertEqual(summary["repair_reject_category"], "budget_exhausted")

    def test_summary_distinguishes_unsupported_issue_reject(self):
        state = workflow.build_initial_state("unsupported issue")
        state["verification_report"] = {
            "status": "retryable_error",
            "repair_scope": "planning",
            "issue_summary": "发现 1 个不支持自动修复的问题。",
            "issues": [
                {
                    "issue_id": "PL-999",
                    "scope": "planning",
                    "target_id": "supply_fan_ctrl",
                    "rule_id": "template_input_interface_mismatch",
                    "message": "template mismatch",
                }
            ],
            "warnings": [],
            "metrics": {},
        }
        state["repair_history"] = [
            {
                "round": 1,
                "scope": "planning",
                "issue_ids": ["PL-999"],
                "target_state_keys": ["architecture_plan", "decomposition_result"],
                "actions": ["当前 repair scope 不支持自动修复规则: template_input_interface_mismatch"],
                "result": "rejected",
                "next_node": "END",
            }
        ]
        state["route_decision"] = {
            "decision": "reject",
            "repair_scope": "planning",
            "next_node": "END",
            "reason": "unsupported_repair_issue",
            "issue_ids": ["PL-999"],
            "retry_exhausted": False,
            "retry_count_for_scope": 1,
            "retry_budget_for_scope": 2,
        }
        state["retry_counts_by_scope"] = {"planning": 1, "assembly": 0, "compile": 0}
        state["retry_count"] = 1

        summary = _summary_for(state)

        self.assertEqual(summary["repair_round_count"], 1)
        self.assertEqual(summary["repair_scopes_seen"], ["planning"])
        self.assertEqual(summary["final_route_decision"], "reject")
        self.assertFalse(summary["retry_exhausted"])
        self.assertEqual(summary["retry_counts_by_scope"], {"planning": 1, "assembly": 0, "compile": 0})
        self.assertEqual(summary["last_repair_issue_ids"], ["PL-999"])
        self.assertEqual(
            summary["last_repair_actions"],
            ["当前 repair scope 不支持自动修复规则: template_input_interface_mismatch"],
        )
        self.assertEqual(summary["reject_reason"], "unsupported_repair_issue")
        self.assertEqual(summary["planning_unresolved_by_type"], {})
        self.assertEqual(summary["ambiguous_signal_count"], 0)
        self.assertEqual(summary["repair_reject_category"], "unsupported_repair_issue")

    def test_summary_counts_planning_unresolved_and_ambiguous_rejects(self):
        state = workflow.build_initial_state("ambiguous reject")
        state["architecture_plan"] = {
            "shared_signal_registry": [
                {
                    "signal_name": "supply_fan_available_flag",
                    "signal_key": "supply_fan_available",
                    "canonical_signal_key": "supply_fan_available",
                    "resolution_status": "ambiguous",
                    "candidate_exporters": ["supply_fan_ctrl", "backup_ctrl"],
                }
            ]
        }
        state["assembled_graph_ir"] = {
            "unresolved_items": [
                {
                    "type": "ambiguous_shared_signal",
                    "severity": "error",
                    "scope": "planning",
                    "signal_name": "supply_fan_available_flag",
                    "canonical_signal_key": "supply_fan_available",
                },
                {
                    "type": "synthetic_shared_signal_source",
                    "severity": "error",
                    "scope": "planning",
                    "signal_name": "heater_enable",
                    "canonical_signal_key": "heater_enable",
                },
            ]
        }
        state["verification_report"] = {
            "status": "retryable_error",
            "repair_scope": "planning",
            "issue_summary": "共享信号歧义未收敛。",
            "issues": [
                {
                    "issue_id": "IR-AMB-001",
                    "scope": "planning",
                    "target_id": "supply_fan_available_flag",
                    "rule_id": "ir.unresolved.ambiguous_shared_signal",
                    "message": "ambiguous shared signal",
                    "repair_payload": {
                        "canonical_signal_key": "supply_fan_available",
                        "resolution_status": "ambiguous",
                    },
                }
            ],
            "warnings": [],
            "metrics": {},
        }
        state["route_decision"] = {
            "decision": "reject",
            "repair_scope": "planning",
            "next_node": "END",
            "reason": "ambiguous_shared_signal_unresolved",
            "issue_ids": ["IR-AMB-001"],
            "retry_exhausted": False,
            "retry_count_for_scope": 1,
            "retry_budget_for_scope": 2,
        }
        state["retry_counts_by_scope"] = {"planning": 1, "assembly": 0, "compile": 0}
        state["retry_count"] = 1

        summary = _summary_for(state)

        self.assertEqual(
            summary["planning_unresolved_by_type"],
            {
                "ambiguous_shared_signal": 1,
                "synthetic_shared_signal_source": 1,
            },
        )
        self.assertEqual(summary["ambiguous_signal_count"], 1)
        self.assertEqual(summary["repair_reject_category"], "ambiguous_shared_signal")


if __name__ == "__main__":
    unittest.main()
