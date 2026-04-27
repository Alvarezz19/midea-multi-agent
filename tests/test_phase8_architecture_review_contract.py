from __future__ import annotations

import sys
import unittest
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph
from langgraph.types import Command


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import workflow
from agents.architecture_feedback_apply_agent import ArchitectureFeedbackApplyAgent
from agents.architecture_review_agent import ArchitectureReviewAgent
from agents.ambiguity_router import AmbiguityRouter
from agents.clarification_apply_agent import ClarificationApplyAgent
from agents.clarification_review_agent import ClarificationReviewAgent
from utils.workflow_runtime import build_configurable_thread


def _base_state(enable_review: bool = False) -> dict:
    state = workflow.build_initial_state(
        "请为 AHU 生成系统骨架",
        enable_hitl_architecture_review=enable_review,
    )
    state["analysis_result"] = {
        "scenario_analysis": {
            "summary": "AHU 系统骨架",
            "system_type": "AHU",
            "input_signals": ["送风温度"],
            "output_signals": ["送风机启停命令"],
            "ambiguities": [],
            "assumptions": [],
            "confidence": 0.9,
        },
        "clarification_signals": {
            "should_clarify": False,
            "signals": [],
            "signal_count": 0,
        },
    }
    state["requirement_spec"] = {
        "schema_version": "3.0",
        "system_type": "AHU",
        "scenario_summary": "AHU 系统骨架",
        "subsystems": [
            {
                "subsystem_id": "supply_fan_ctrl",
                "subsystem_type": "supply_fan_control",
                "goal": "送风机控制",
                "page_hint": "控制",
                "priority": 1,
                "preferred_templates": [],
                "imports": ["schedule_enable"],
                "exports": ["supply_fan_available_flag"],
            }
        ],
        "signals": {"inputs": ["送风温度"], "outputs": ["送风机启停命令"], "software_points": [], "alarm_points": []},
        "required_pages": ["控制"],
        "global_modes": [],
        "ambiguities": [],
        "assumptions": [],
        "acceptance_criteria": [],
        "confidence": 0.9,
        "warnings": [],
    }
    return state


class _StubAnalysis:
    def __call__(self, state):
        state.update(_base_state(enable_review=bool(state.get("enable_hitl_architecture_review", False))))
        state["current_step"] = "analysis_completed"
        return state


class _StubRetrieval:
    def __call__(self, state):
        state["retrieval_bundle"] = {"source": "stub"}
        state["current_step"] = "retrieval_completed"
        return state


class _StubArchitecturePlanning:
    def __call__(self, state):
        history = list(state.get("debug_history", []) or [])
        patch = state.get("architecture_feedback_patch", {}) or {}
        patch_decision = str(patch.get("decision", "") or "").strip()
        if patch_decision in {"feedback", "clarify"}:
            history.append("architecture_run_2")
            page_labels = ["控制", "总览"]
            constraint = {"summary": "补充总览页约束"}
        else:
            history.append("architecture_run_1")
            page_labels = ["控制"]
            constraint = {"summary": "保持控制页为主"}

        state["debug_history"] = history
        state["decomposition_result"] = {
            "pages": [{"page_id": label, "label": label} for label in page_labels],
            "subsystem_descriptors": [
                {
                    "subsystem_id": "supply_fan_ctrl",
                    "interface_bindings": [
                        {
                            "signal_name": "schedule_enable",
                            "signal_key": "schedule_enable",
                            "canonical_signal_key": "schedule_enable",
                            "direction": "input",
                            "binding_kind": "external_input",
                            "allowed_external": True,
                            "owner_subsystem_id": "",
                            "port_index": 0,
                            "candidate_exporters": [],
                        },
                        {
                            "signal_name": "supply_fan_available_flag",
                            "signal_key": "supply_fan_available_flag",
                            "canonical_signal_key": "supply_fan_available",
                            "direction": "output",
                            "binding_kind": "shared_signal",
                            "allowed_external": False,
                            "owner_subsystem_id": "supply_fan_ctrl",
                            "port_index": 1,
                            "candidate_exporters": ["supply_fan_ctrl"],
                        },
                    ],
                    "imports": ["schedule_enable"],
                    "exports": ["supply_fan_available_flag"],
                }
            ],
            "shared_signal_registry": [
                {
                    "signal_name": "supply_fan_available_flag",
                    "signal_key": "supply_fan_available_flag",
                    "canonical_signal_key": "supply_fan_available",
                    "owner_subsystem_id": "supply_fan_ctrl",
                    "candidate_exporters": ["supply_fan_ctrl"],
                    "consumers": [],
                }
            ],
            "template_needs": [],
            "planning_order": ["supply_fan_ctrl"],
            "warnings": [],
        }
        state["architecture_plan"] = {
            "goal": "ahu-architecture",
            "pages": [{"page_id": label, "label": label} for label in page_labels],
            "subsystem_slots": [{"subsystem_id": "supply_fan_ctrl", "page_id": "控制"}],
            "shared_signal_registry": [
                {
                    "signal_name": "supply_fan_available_flag",
                    "signal_key": "supply_fan_available_flag",
                    "canonical_signal_key": "supply_fan_available",
                    "owner_subsystem_id": "supply_fan_ctrl",
                    "candidate_exporters": ["supply_fan_ctrl"],
                    "consumers": [],
                }
            ],
            "global_constraints": [constraint],
            "naming_strategy": {},
            "layout_strategy": {},
            "pattern_bindings": [],
            "warnings": [],
        }
        state["current_step"] = "architecture_planned"
        return state


class _StubSubsystemPlanning:
    def __call__(self, state):
        history = list(state.get("debug_history", []) or [])
        pages = [page.get("label", "") for page in (state.get("architecture_plan", {}) or {}).get("pages", []) or []]
        history.append(f"subsystem_after_{'+'.join(pages)}")
        state["debug_history"] = history
        state["subsystem_plan_map"] = {"supply_fan_ctrl": {"page_labels": pages}}
        state["current_step"] = "subsystem_planned"
        return state


class _StubAssembly:
    def __call__(self, state):
        state["assembled_graph_ir"] = {"unresolved_items": []}
        state["current_step"] = "global_assembly_completed"
        return state


class _StubCoding:
    def __call__(self, state):
        state["compiled_artifact"] = {"compile_report": {"page_count": 0, "subflow_count": 0, "node_count": 0}}
        state["current_step"] = "coding_completed"
        return state


class _StubVerification:
    def __call__(self, state):
        state["verification_report"] = {
            "status": "passed",
            "repair_scope": "none",
            "issue_summary": "ok",
            "issues": [],
            "warnings": [],
            "metrics": {},
        }
        state["final_output"] = {"status": "ok"}
        state["current_step"] = "verification_completed"
        return state


class _StubRepairRouter:
    def __call__(self, state):
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
        return state


class _StubRepairAgent:
    def __call__(self, state):
        return state


def _assert_no_compat_fields(state: dict) -> None:
    assert "retrieval_context" not in state
    assert "execution_plan" not in state
    assert "generated_code" not in state
    assert "execution_result" not in state
    assert "validation_result" not in state
    assert "next_step" not in state


def _build_architecture_review_graph():
    nodes = {
        "analysis": _StubAnalysis(),
        "ambiguity_router": AmbiguityRouter(),
        "clarification_review": ClarificationReviewAgent(),
        "clarification_apply": ClarificationApplyAgent(),
        "retrieval": _StubRetrieval(),
        "architecture_planning": _StubArchitecturePlanning(),
        "architecture_review": ArchitectureReviewAgent(),
        "architecture_feedback_apply": ArchitectureFeedbackApplyAgent(),
        "subsystem_planning": _StubSubsystemPlanning(),
        "global_assembly": _StubAssembly(),
        "coding": _StubCoding(),
        "verification": _StubVerification(),
        "repair_router": _StubRepairRouter(),
        "repair_agent": _StubRepairAgent(),
    }
    return workflow.populate_phase4_workflow(
        StateGraph(workflow.WorkflowState),
        nodes,
        enable_repair_loop=True,
    ).compile(checkpointer=InMemorySaver())


class Phase8ArchitectureReviewContractTests(unittest.TestCase):
    def test_architecture_review_builds_user_readable_summary(self):
        state = _base_state(enable_review=False)
        state["architecture_plan"] = {
            "goal": "ahu-architecture",
            "pages": [{"page_id": "control", "label": "控制"}],
            "subsystem_slots": [{"subsystem_id": "supply_fan_ctrl", "page_id": "control"}],
            "shared_signal_registry": [
                {
                    "signal_name": "supply_fan_available_flag",
                    "signal_key": "supply_fan_available_flag",
                    "owner_subsystem_id": "supply_fan_ctrl",
                    "consumers": ["heater_ctrl"],
                }
            ],
            "global_constraints": [{"summary": "控制页必须保留"}],
        }
        state["decomposition_result"] = {
            "subsystem_descriptors": [{"subsystem_id": "supply_fan_ctrl"}],
            "pages": [{"page_id": "control", "label": "控制"}],
        }

        result = ArchitectureReviewAgent()(state)

        self.assertEqual(result["review_status"], "assumed")
        self.assertEqual(result["hitl_stage"], "architecture_review")
        self.assertIn("页面列表：控制", result["review_request"]["context_summary"])
        self.assertIn("子系统列表：supply_fan_ctrl", result["review_request"]["context_summary"])
        self.assertIn("共享信号摘要", result["review_request"]["context_summary"])

    def test_architecture_feedback_apply_rejects_direct_architecture_patch(self):
        state = _base_state()
        state["review_id"] = "architecture-001"
        state["review_response"] = {
            "decision": "feedback",
            "answers": [],
            "feedback": "",
            "updated_constraints": {
                "required_pages": ["控制", "总览"],
                "architecture_plan": {"goal": "forbidden"},
            },
            "review_id": "architecture-001",
        }

        with self.assertRaisesRegex(ValueError, "review_patch_forbidden:architecture_plan"):
            ArchitectureFeedbackApplyAgent()(state)

    def test_architecture_feedback_loops_back_to_architecture_planning_before_subsystem_planning(self):
        app = _build_architecture_review_graph()
        config = {"configurable": build_configurable_thread("phase8-architecture-contract")}
        initial_state = workflow.build_initial_state(
            "请为 AHU 生成系统骨架",
            enable_hitl_architecture_review=True,
        )

        first_result = app.invoke(initial_state, config)

        self.assertIn("__interrupt__", first_result)
        paused_state = app.get_state(config).values
        _assert_no_compat_fields(paused_state)
        self.assertEqual(paused_state["debug_history"], ["architecture_run_1"])
        self.assertEqual(paused_state["review_request"]["stage"], "architecture_review")
        self.assertIn("页面列表：控制", paused_state["review_request"]["context_summary"])

        second_pause = app.invoke(
            Command(
                resume={
                    "decision": "feedback",
                    "answers": ["请增加总览页"],
                    "feedback": "结构上需要在子系统规划前补一个总览页。",
                    "updated_constraints": {
                        "required_pages": ["控制", "总览"],
                        "assumptions": ["增加总览页后再进入子系统规划。"],
                    },
                    "review_id": paused_state["review_id"],
                }
            ),
            config,
        )

        self.assertIn("__interrupt__", second_pause)
        second_state = app.get_state(config).values
        _assert_no_compat_fields(second_state)
        self.assertEqual(
            second_state["debug_history"],
            ["architecture_run_1", "architecture_run_2"],
        )
        self.assertEqual(
            [page["label"] for page in second_state["architecture_plan"]["pages"]],
            ["控制", "总览"],
        )
        self.assertEqual(second_state["architecture_feedback_patch"]["decision"], "feedback")
        self.assertEqual(second_state["review_request"]["stage"], "architecture_review")
        self.assertEqual(second_state["subsystem_plan_map"], {})

        final_result = app.invoke(
            Command(
                resume={
                    "decision": "approve",
                    "answers": [],
                    "feedback": "",
                    "updated_constraints": {},
                    "review_id": second_state["review_id"],
                }
            ),
            config,
        )

        _assert_no_compat_fields(final_result)
        self.assertEqual(
            final_result["debug_history"],
            ["architecture_run_1", "architecture_run_2", "subsystem_after_控制+总览"],
        )
        self.assertEqual(final_result["subsystem_plan_map"]["supply_fan_ctrl"]["page_labels"], ["控制", "总览"])
        self.assertEqual(final_result["route_decision"]["decision"], "accept")


if __name__ == "__main__":
    unittest.main()
