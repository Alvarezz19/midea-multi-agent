from __future__ import annotations

import sys
import unittest
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphInterrupt
from langgraph.graph import StateGraph
from langgraph.types import Command, interrupt


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import workflow
import workflow_trace
from agents.ambiguity_router import AmbiguityRouter
from agents.architecture_feedback_apply_agent import ArchitectureFeedbackApplyAgent
from agents.architecture_review_agent import ArchitectureReviewAgent
from agents.clarification_apply_agent import ClarificationApplyAgent
from agents.clarification_review_agent import ClarificationReviewAgent
from utils.workflow_runtime import build_configurable_thread


def _ambiguous_requirement_state(review_enabled: bool = False) -> dict:
    state = workflow.build_initial_state(
        "请生成一个控制程序",
        enable_hitl_clarification=review_enabled,
    )
    state["analysis_result"] = {
        "scenario_analysis": {
            "summary": "控制程序",
            "system_type": "",
            "input_signals": [],
            "output_signals": [],
            "ambiguities": ["系统类型未明确"],
            "assumptions": [],
            "confidence": 0.2,
        },
        "clarification_signals": {
            "should_clarify": True,
            "signals": [
                {"code": "missing_system_type", "severity": "high", "message": "系统类型未明确。"},
                {"code": "missing_key_subsystems", "severity": "high", "message": "未识别出稳定的子系统边界。"},
            ],
            "signal_count": 2,
        },
    }
    state["requirement_spec"] = {
        "schema_version": "3.0",
        "system_type": "",
        "scenario_summary": "控制程序",
        "subsystems": [],
        "signals": {"inputs": [], "outputs": [], "software_points": [], "alarm_points": []},
        "required_pages": [],
        "global_modes": [],
        "ambiguities": ["系统类型未明确"],
        "assumptions": [],
        "acceptance_criteria": [],
        "confidence": 0.2,
        "warnings": ["未能从场景分析中识别系统类型。"],
    }
    return state


class _StubAnalysis:
    def __call__(self, state):
        history = list(state.get("debug_history", []) or [])
        history.append("analysis_run")
        state["debug_history"] = history
        state.update(_ambiguous_requirement_state(review_enabled=bool(state.get("enable_hitl_clarification", False))))
        state["debug_history"] = history
        state["current_step"] = "analysis_completed"
        return state


class _StubRetrieval:
    def __call__(self, state):
        state["retrieval_bundle"] = {"source": "stub"}
        state["retrieval_context"] = {"source": "stub"}
        state["current_step"] = "retrieval_completed"
        return state


class _StubArchitecture:
    def __call__(self, state):
        state["decomposition_result"] = {"pages": [], "subsystem_descriptors": [], "shared_signal_registry": []}
        state["architecture_plan"] = {"goal": "stub", "pages": [], "subsystem_slots": [], "shared_signal_registry": []}
        state["current_step"] = "architecture_planned"
        return state


class _StubSubsystem:
    def __call__(self, state):
        state["subsystem_plan_map"] = {}
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


def _build_clarification_graph():
    nodes = {
        "analysis": _StubAnalysis(),
        "ambiguity_router": AmbiguityRouter(),
        "clarification_review": ClarificationReviewAgent(),
        "clarification_apply": ClarificationApplyAgent(),
        "retrieval": _StubRetrieval(),
        "architecture_planning": _StubArchitecture(),
        "architecture_review": ArchitectureReviewAgent(),
        "architecture_feedback_apply": ArchitectureFeedbackApplyAgent(),
        "subsystem_planning": _StubSubsystem(),
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


class Phase8ClarificationContractTests(unittest.TestCase):
    def test_ambiguity_router_marks_high_ambiguity_for_review(self):
        state = _ambiguous_requirement_state()

        result = AmbiguityRouter()(state)

        self.assertTrue(result["review_required"])
        self.assertEqual(result["hitl_stage"], "clarification_review")
        self.assertEqual(result["review_status"], "pending")

    def test_clarification_review_uses_conservative_bypass_when_hitl_disabled(self):
        state = _ambiguous_requirement_state(review_enabled=False)
        state["review_required"] = True

        result = ClarificationReviewAgent()(state)

        self.assertEqual(result["review_status"], "assumed")
        self.assertEqual(result["hitl_stage"], "clarification_review")
        self.assertEqual(result["review_request"]["stage"], "clarification_review")
        self.assertEqual(result["review_history"][-1]["status"], "assumed")

    def test_clarification_apply_rejects_non_requirement_patch_keys(self):
        state = _ambiguous_requirement_state()
        state["review_id"] = "clarification-001"
        state["review_response"] = {
            "decision": "clarify",
            "answers": [],
            "feedback": "",
            "updated_constraints": {
                "required_pages": ["控制"],
                "architecture_plan": {"goal": "forbidden"},
            },
            "review_id": "clarification-001",
        }

        with self.assertRaisesRegex(ValueError, "review_patch_forbidden:architecture_plan"):
            ClarificationApplyAgent()(state)

    def test_trace_wrapper_marks_graph_interrupt_as_interrupted(self):
        records: list[dict] = []
        builder = StateGraph(dict)
        builder.add_node(
            "clarification_review",
            workflow_trace._wrap_node(
                "clarification_review",
                lambda state: interrupt({"question": "clarify?"}),
                records,
            ),
        )
        builder.set_entry_point("clarification_review")
        graph = builder.compile(checkpointer=InMemorySaver())
        result = graph.invoke(
            {"hitl_stage": "clarification_review", "review_id": "clarification-001"},
            {"configurable": build_configurable_thread("phase8-interrupt-trace")},
        )

        self.assertIn("__interrupt__", result)
        self.assertEqual(records[-1]["status"], "interrupted")
        self.assertEqual(records[-1]["output"]["interrupt_type"], "GraphInterrupt")

    def test_pause_resume_keeps_analysis_single_run_and_applies_only_requirement_side_updates(self):
        app = _build_clarification_graph()
        config = {"configurable": build_configurable_thread("phase8-clarification-contract")}
        initial_state = workflow.build_initial_state(
            "请生成一个控制程序",
            enable_hitl_clarification=True,
        )

        first_result = app.invoke(initial_state, config)

        self.assertIn("__interrupt__", first_result)
        paused_state = app.get_state(config).values
        self.assertEqual(paused_state["debug_history"], ["analysis_run"])
        self.assertEqual(paused_state["review_request"]["stage"], "clarification_review")
        self.assertEqual(paused_state["retrieval_bundle"], {})

        final_result = app.invoke(
            Command(
                resume={
                    "decision": "clarify",
                    "answers": ["系统类型为 AHU", "必须包含控制页和定时页"],
                    "feedback": "按 AHU 标准控制继续。",
                    "updated_constraints": {
                        "system_type": "AHU",
                        "required_pages": ["控制", "定时"],
                        "assumptions": ["按 AHU 标准控制继续。"],
                    },
                    "review_id": paused_state["review_id"],
                }
            ),
            config,
        )

        self.assertEqual(final_result["debug_history"], ["analysis_run"])
        self.assertEqual(final_result["clarification_round"], 1)
        self.assertEqual(final_result["requirement_spec"]["system_type"], "AHU")
        self.assertEqual(final_result["requirement_spec"]["required_pages"], ["控制", "定时"])
        self.assertEqual(final_result["retrieval_bundle"]["source"], "stub")
        self.assertEqual(final_result["architecture_plan"]["goal"], "stub")


if __name__ == "__main__":
    unittest.main()
