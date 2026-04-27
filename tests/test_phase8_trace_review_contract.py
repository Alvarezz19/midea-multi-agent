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

import workflow
import workflow_trace
from agents.architecture_feedback_apply_agent import ArchitectureFeedbackApplyAgent
from agents.clarification_apply_agent import ClarificationApplyAgent


class Phase8TraceReviewContractTests(unittest.TestCase):
    def test_trace_summary_marks_graph_interrupt_as_interrupted_instead_of_failed(self):
        state = workflow.build_initial_state("phase8 interrupted")
        state["review_required"] = True
        state["review_enabled"] = True
        state["review_status"] = "pending"
        state["review_request"] = {
            "review_id": "architecture-001",
            "stage": "architecture_review",
            "question": "请确认结构骨架。",
            "options": [],
            "context_summary": "页面列表：控制",
            "created_at": "2026-04-17T10:00:00+00:00",
        }
        state["review_id"] = "architecture-001"
        state["__interrupt__"] = [{"value": "paused"}]

        summary = workflow_trace._build_trace_summary(
            user_query="phase8 interrupted",
            node_io_records=[
                {"node_name": "analysis", "status": "success", "output": {}},
                {"node_name": "architecture_review", "status": "interrupted", "output": {}},
            ],
            final_state=state,
            total_elapsed_seconds=0.12,
        )

        self.assertEqual(summary["workflow_status"], "interrupted")
        self.assertEqual(summary["hitl_stage"], "architecture_review")
        self.assertEqual(summary["review_status"], "interrupted")
        self.assertEqual(summary["failed_node"], "")

    def test_trace_run_persists_review_records_and_indexes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            trace_root = Path(temp_dir)
            review_request = {
                "review_id": "architecture-001",
                "stage": "architecture_review",
                "question": "请确认结构骨架。",
                "options": [],
                "context_summary": "页面列表：控制",
                "created_at": "2026-04-17T10:00:00+00:00",
            }
            review_response = {
                "decision": "feedback",
                "answers": ["请增加总览页"],
                "feedback": "增加总览页后再进入子系统规划。",
                "updated_constraints": {"required_pages": ["控制", "总览"]},
                "review_id": "architecture-001",
            }

            class FakeApp:
                def invoke(self, initial_state, config=None):
                    state = dict(initial_state)
                    state["review_required"] = True
                    state["review_enabled"] = False
                    state["review_status"] = "applied"
                    state["hitl_stage"] = "none"
                    state["review_id"] = "architecture-001"
                    state["review_request"] = review_request
                    state["review_response"] = review_response
                    state["review_history"] = [
                        {
                            "review_id": "architecture-001",
                            "stage": "architecture_review",
                            "status": "applied",
                            "request": review_request,
                            "response": review_response,
                            "created_at": "2026-04-17T10:00:00+00:00",
                            "updated_at": "2026-04-17T10:01:00+00:00",
                        }
                    ]
                    state["verification_report"] = {
                        "status": "passed",
                        "repair_scope": "none",
                        "issue_summary": "ok",
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
                    state["final_output"] = {"status": "ok"}
                    return state

            class FakeWorkflow:
                def compile(self, **kwargs):
                    return FakeApp()

            with patch.object(workflow_trace, "TRACE_OUTPUT_ROOT", str(trace_root)), patch.object(
                workflow_trace,
                "create_workflow",
                return_value=FakeWorkflow(),
            ):
                result = workflow_trace.run_workflow("fan control", thread_id="phase8-review-thread")

            trace_info = result["final_output"]["workflow_trace"]
            self.assertTrue(Path(trace_info["review_records_json"]).exists())
            self.assertTrue(Path(trace_info["approval_record_json"]).exists())
            self.assertTrue(Path(trace_info["review_attempt_index_json"]).exists())
            self.assertTrue(Path(trace_info["review_thread_index_json"]).exists())
            self.assertEqual(len(trace_info["review_record_jsons"]), 1)
            self.assertTrue(Path(trace_info["review_record_jsons"][0]).exists())

            summary = json.loads(Path(trace_info["summary_json"]).read_text(encoding="utf-8"))
            self.assertEqual(summary["approval_record_json"], trace_info["approval_record_json"])
            self.assertEqual(summary["review_id"], "architecture-001")

            approval_record = json.loads(Path(trace_info["approval_record_json"]).read_text(encoding="utf-8"))
            self.assertEqual(approval_record["review_id"], "architecture-001")
            self.assertEqual(approval_record["review_stage"], "architecture_review")
            self.assertEqual(approval_record["decision"], "feedback")
            self.assertEqual(approval_record["resume_value"]["review_id"], "architecture-001")

            attempt_index = json.loads(Path(trace_info["review_attempt_index_json"]).read_text(encoding="utf-8"))
            self.assertEqual(attempt_index["thread_id"], "phase8-review-thread")
            self.assertEqual(attempt_index["review_count"], 1)
            self.assertEqual(attempt_index["reviews"][0]["review_id"], "architecture-001")

            thread_index = json.loads(Path(trace_info["review_thread_index_json"]).read_text(encoding="utf-8"))
            self.assertEqual(thread_index["thread_id"], "phase8-review-thread")
            self.assertEqual(len(thread_index["reviews"]), 1)
            self.assertEqual(thread_index["reviews"][0]["review_stage"], "architecture_review")

    def test_apply_agents_promote_review_history_to_final_status(self):
        clarification_state = workflow.build_initial_state("clarification")
        clarification_state["review_id"] = "clarification-001"
        clarification_state["review_request"] = {
            "review_id": "clarification-001",
            "stage": "clarification_review",
            "question": "请补充系统类型。",
            "options": [],
            "context_summary": "系统类型未明确。",
            "created_at": "2026-04-17T10:00:00+00:00",
        }
        clarification_state["review_response"] = {
            "decision": "clarify",
            "answers": ["系统类型为 AHU"],
            "feedback": "按 AHU 标准继续。",
            "updated_constraints": {"system_type": "AHU"},
            "review_id": "clarification-001",
        }
        clarification_state["review_history"] = [
            {
                "review_id": "clarification-001",
                "stage": "clarification_review",
                "status": "answered",
                "request": clarification_state["review_request"],
                "response": clarification_state["review_response"],
                "created_at": "2026-04-17T10:00:00+00:00",
                "updated_at": "2026-04-17T10:00:30+00:00",
            }
        ]
        clarification_state["analysis_result"] = {"scenario_analysis": {}, "clarification_signals": {"signals": []}}
        clarification_state["requirement_spec"] = workflow.build_initial_state("clarification")["requirement_spec"]

        clarification_result = ClarificationApplyAgent()(clarification_state)
        self.assertEqual(clarification_result["review_history"][-1]["status"], "applied")

        architecture_state = workflow.build_initial_state("architecture")
        architecture_state["review_id"] = "architecture-001"
        architecture_state["review_request"] = {
            "review_id": "architecture-001",
            "stage": "architecture_review",
            "question": "请确认结构骨架。",
            "options": [],
            "context_summary": "页面列表：控制",
            "created_at": "2026-04-17T10:00:00+00:00",
        }
        architecture_state["review_response"] = {
            "decision": "approve",
            "answers": [],
            "feedback": "",
            "updated_constraints": {},
            "review_id": "architecture-001",
        }
        architecture_state["review_history"] = [
            {
                "review_id": "architecture-001",
                "stage": "architecture_review",
                "status": "answered",
                "request": architecture_state["review_request"],
                "response": architecture_state["review_response"],
                "created_at": "2026-04-17T10:00:00+00:00",
                "updated_at": "2026-04-17T10:00:30+00:00",
            }
        ]

        architecture_result = ArchitectureFeedbackApplyAgent()(architecture_state)
        self.assertEqual(architecture_result["review_history"][-1]["status"], "applied")

    def test_architecture_feedback_apply_keeps_original_request_in_history(self):
        state = workflow.build_initial_state("architecture")
        state["review_id"] = "architecture-001"
        state["review_request"] = {
            "review_id": "architecture-001",
            "stage": "architecture_review",
            "question": "请确认结构骨架。",
            "options": [],
            "context_summary": "页面列表：控制",
            "created_at": "2026-04-17T10:00:00+00:00",
        }
        state["review_response"] = {
            "decision": "feedback",
            "answers": ["请增加总览页"],
            "feedback": "增加总览页后再继续。",
            "updated_constraints": {"required_pages": ["控制", "总览"]},
            "review_id": "architecture-001",
        }
        state["review_history"] = [
            {
                "review_id": "architecture-001",
                "stage": "architecture_review",
                "status": "answered",
                "request": state["review_request"],
                "response": state["review_response"],
                "created_at": "2026-04-17T10:00:00+00:00",
                "updated_at": "2026-04-17T10:00:30+00:00",
            }
        ]

        result = ArchitectureFeedbackApplyAgent()(state)

        self.assertEqual(result["review_request"]["stage"], "none")
        self.assertEqual(result["review_history"][-1]["request"]["review_id"], "architecture-001")
        self.assertEqual(result["review_history"][-1]["request"]["question"], "请确认结构骨架。")
        self.assertEqual(result["review_history"][-1]["response"]["decision"], "feedback")


if __name__ == "__main__":
    unittest.main()
