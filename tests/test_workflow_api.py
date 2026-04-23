from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.main import create_app
from app.repositories.workflow_run_repository import WorkflowRunRepository
from app.services.workflow_service import WorkflowService


class FakeRunner:
    def __init__(self) -> None:
        self.states: dict[str, dict[str, Any]] = {}
        self._tmpdir = tempfile.TemporaryDirectory()

    def _trace_files(self, *, thread_id: str, attempt_id: str, workflow_status: str) -> dict[str, Any]:
        trace_dir = Path(self._tmpdir.name) / f"trace-{attempt_id}"
        trace_dir.mkdir(parents=True, exist_ok=True)
        summary_json = trace_dir / "workflow_node_io_record.json"
        summary_json.write_text(
            json.dumps(
                {
                    "thread_id": thread_id,
                    "attempt_id": attempt_id,
                    "workflow_status": workflow_status,
                    "last_successful_node": "architecture_review",
                    "node_count": 3,
                    "nodes": [{"node_name": "analysis"}, {"node_name": "architecture_review"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return {
            "thread_id": thread_id,
            "attempt_id": attempt_id,
            "trace_dir": str(trace_dir),
            "summary_json": str(summary_json),
        }

    def run(
        self,
        *,
        attempt_id: str,
        thread_id: str,
        user_query: str,
        runtime_metadata: dict[str, Any] | None,
        enable_hitl_clarification: bool,
        enable_hitl_architecture_review: bool,
    ):
        trace_files = self._trace_files(thread_id=thread_id, attempt_id=attempt_id, workflow_status="interrupted")
        state = {
            "user_query": user_query,
            "current_step": "architecture_review_prepared",
            "review_id": "architecture-001",
            "review_status": "pending",
            "review_request": {
                "review_id": "architecture-001",
                "stage": "architecture_review",
                "question": "请确认结构骨架。",
                "options": [{"label": "批准继续", "value": "approve", "description": "继续"}],
                "context_summary": "页面列表：控制",
            },
            "__interrupt__": [{"value": "paused"}],
            "final_output": {
                "workflow_trace": trace_files,
            },
        }
        self.states[thread_id] = state
        return type("RunResult", (), {"state": state, "trace_files": trace_files})()

    def resume(
        self,
        *,
        attempt_id: str,
        thread_id: str,
        user_query: str,
        resume_payload: dict[str, Any],
        runtime_metadata: dict[str, Any] | None,
    ):
        trace_files = self._trace_files(thread_id=thread_id, attempt_id=attempt_id, workflow_status="completed")
        state = {
            "user_query": user_query,
            "current_step": "verification_completed",
            "review_id": resume_payload["review_id"],
            "review_status": "applied",
            "review_request": {
                "review_id": "",
                "stage": "none",
                "question": "",
                "options": [],
                "context_summary": "",
            },
            "verification_report": {
                "status": "passed",
                "repair_scope": "none",
                "issue_summary": "ok",
                "issues": [],
                "warnings": [],
                "metrics": {},
            },
            "route_decision": {
                "decision": "accept",
                "repair_scope": "none",
                "next_node": "END",
                "reason": "verification_passed",
                "issue_ids": [],
            },
            "final_output": {
                "json_text": "{\"ok\": true}",
                "compile_report": {"page_count": 1, "subflow_count": 0, "node_count": 2, "warnings": []},
                "verification_report": {
                    "status": "passed",
                    "repair_scope": "none",
                    "issue_summary": "ok",
                    "issues": [],
                    "warnings": [],
                    "metrics": {},
                },
                "workflow_trace": {
                    **trace_files,
                },
            },
        }
        self.states[thread_id] = state
        return type("RunResult", (), {"state": state, "trace_files": trace_files})()

    def get_state_snapshot(self, *, thread_id: str) -> dict[str, Any]:
        return {"values": self.states.get(thread_id, {})}

    def get_state_history(self, *, thread_id: str, limit: int = 10) -> list[dict[str, Any]]:
        return [
            {
                "created_at": "2026-04-22T10:00:00Z",
                "next": [],
                "metadata": {"step": 1},
                "values": self.states.get(thread_id, {}),
            }
        ][:limit]

    def health_check(self) -> dict[str, Any]:
        return {"checkpointer_ready": True}


class WorkflowApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = FakeRunner()
        service = WorkflowService(
            repository=WorkflowRunRepository(),
            runner=self.runner,
            task_scheduler=lambda target, *args, **kwargs: target(*args, **kwargs),
        )
        self.client = TestClient(create_app(service=service))

    def tearDown(self) -> None:
        self.runner._tmpdir.cleanup()

    def test_run_interrupt_then_resume_and_fetch_result(self):
        create_response = self.client.post(
            "/api/workflow/runs",
            json={
                "user_query": "为 AHU 生成控制骨架",
                "enable_hitl_architecture_review": True,
            },
        )
        self.assertEqual(create_response.status_code, 200)
        payload = create_response.json()
        thread_id = payload["thread_id"]
        attempt_id = payload["attempt_id"]

        thread_response = self.client.get(f"/api/workflow/threads/{thread_id}")
        self.assertEqual(thread_response.status_code, 200)
        self.assertEqual(thread_response.json()["latest_status"], "interrupted")

        detail_response = self.client.get(f"/api/workflow/threads/{thread_id}/attempts/{attempt_id}")
        self.assertEqual(detail_response.status_code, 200)
        detail = detail_response.json()
        self.assertEqual(detail["status"], "interrupted")
        self.assertEqual(detail["review"]["review_id"], "architecture-001")
        self.assertEqual(detail["review"]["stage"], "architecture_review")

        resume_response = self.client.post(
            f"/api/workflow/threads/{thread_id}/resume",
            json={
                "attempt_id": attempt_id,
                "review_id": "architecture-001",
                "decision": "approve",
                "answers": [],
                "feedback": "",
                "updated_constraints": {},
            },
        )
        self.assertEqual(resume_response.status_code, 200)
        self.assertEqual(resume_response.json()["status"], "running")

        result_response = self.client.get(f"/api/workflow/threads/{thread_id}/attempts/{attempt_id}/result")
        self.assertEqual(result_response.status_code, 200)
        result = result_response.json()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["result"]["verification_report"]["status"], "passed")
        self.assertEqual(result["result"]["json_text"], "{\"ok\": true}")

        attempts_response = self.client.get(f"/api/workflow/threads/{thread_id}/attempts")
        self.assertEqual(attempts_response.status_code, 200)
        self.assertEqual(len(attempts_response.json()["items"]), 1)

    def test_resume_rejects_mismatched_review_id(self):
        create_response = self.client.post(
            "/api/workflow/runs",
            json={"user_query": "为 AHU 生成控制骨架"},
        )
        payload = create_response.json()
        thread_id = payload["thread_id"]
        attempt_id = payload["attempt_id"]

        resume_response = self.client.post(
            f"/api/workflow/threads/{thread_id}/resume",
            json={
                "attempt_id": attempt_id,
                "review_id": "wrong-review",
                "decision": "approve",
                "answers": [],
                "feedback": "",
                "updated_constraints": {},
            },
        )
        self.assertEqual(resume_response.status_code, 409)
        self.assertEqual(resume_response.json()["error"]["code"], "conflict")

    def test_create_run_rejects_active_attempt_on_same_thread(self):
        create_response = self.client.post(
            "/api/workflow/runs",
            json={"user_query": "为 AHU 生成控制骨架", "thread_id": "thread-active"},
        )
        self.assertEqual(create_response.status_code, 200)

        conflict_response = self.client.post(
            "/api/workflow/runs",
            json={"user_query": "再次生成", "thread_id": "thread-active"},
        )
        self.assertEqual(conflict_response.status_code, 409)
        error = conflict_response.json()["error"]
        self.assertEqual(error["code"], "conflict")
        self.assertEqual(error["details"]["active_status"], "interrupted")

    def test_resume_rejects_mismatched_attempt_id(self):
        create_response = self.client.post(
            "/api/workflow/runs",
            json={"user_query": "为 AHU 生成控制骨架"},
        )
        payload = create_response.json()
        thread_id = payload["thread_id"]

        resume_response = self.client.post(
            f"/api/workflow/threads/{thread_id}/resume",
            json={
                "attempt_id": "wrong-attempt",
                "review_id": "architecture-001",
                "decision": "approve",
                "answers": [],
                "feedback": "",
                "updated_constraints": {},
            },
        )
        self.assertEqual(resume_response.status_code, 409)
        self.assertEqual(resume_response.json()["error"]["details"]["active_attempt_id"], payload["attempt_id"])

    def test_terminal_attempt_cannot_resume_again(self):
        create_response = self.client.post(
            "/api/workflow/runs",
            json={"user_query": "为 AHU 生成控制骨架"},
        )
        payload = create_response.json()
        thread_id = payload["thread_id"]
        attempt_id = payload["attempt_id"]

        resume_response = self.client.post(
            f"/api/workflow/threads/{thread_id}/resume",
            json={
                "attempt_id": attempt_id,
                "review_id": "architecture-001",
                "decision": "approve",
                "answers": [],
                "feedback": "",
                "updated_constraints": {},
            },
        )
        self.assertEqual(resume_response.status_code, 200)

        second_resume_response = self.client.post(
            f"/api/workflow/threads/{thread_id}/resume",
            json={
                "attempt_id": attempt_id,
                "review_id": "architecture-001",
                "decision": "approve",
                "answers": [],
                "feedback": "",
                "updated_constraints": {},
            },
        )
        self.assertEqual(second_resume_response.status_code, 409)
        self.assertEqual(second_resume_response.json()["error"]["details"]["status"], "completed")

    def test_trace_and_state_history_endpoints(self):
        create_response = self.client.post(
            "/api/workflow/runs",
            json={"user_query": "为 AHU 生成控制骨架"},
        )
        payload = create_response.json()
        thread_id = payload["thread_id"]
        attempt_id = payload["attempt_id"]

        trace_response = self.client.get(f"/api/workflow/threads/{thread_id}/attempts/{attempt_id}/trace")
        self.assertEqual(trace_response.status_code, 200)
        trace = trace_response.json()
        self.assertEqual(trace["summary"]["workflow_status"], "interrupted")
        self.assertEqual(trace["summary"]["node_count"], 3)

        history_response = self.client.get(f"/api/workflow/threads/{thread_id}/attempts/{attempt_id}/state-history")
        self.assertEqual(history_response.status_code, 200)
        self.assertEqual(len(history_response.json()["items"]), 1)

    def test_validation_error_uses_stable_error_envelope(self):
        response = self.client.post("/api/workflow/runs", json={"user_query": ""})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "validation_error")


if __name__ == "__main__":
    unittest.main()
