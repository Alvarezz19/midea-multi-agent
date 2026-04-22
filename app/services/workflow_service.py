from __future__ import annotations

from datetime import datetime, timezone
from threading import Thread
from typing import Any, Callable
from uuid import uuid4

import chromadb

import config
from app.repositories.workflow_run_repository import AttemptRecord, WorkflowRunRepository
from app.services.checkpointer_factory import CheckpointerFactory
from app.services.workflow_runner import WorkflowRuntimeRunner
from app.services.workflow_state_projection import (
    build_attempt_detail,
    build_attempt_list_item,
    build_attempt_result,
    build_thread_overview,
    infer_attempt_status,
)
from utils.phase3_contracts import normalize_review_response
from utils.trace_index import generate_attempt_id


class WorkflowServiceError(Exception):
    code = "workflow_error"


class NotFoundError(WorkflowServiceError):
    code = "not_found"


class ConflictError(WorkflowServiceError):
    code = "conflict"


def default_task_scheduler(target: Callable[..., None], *args: Any, **kwargs: Any) -> Thread:
    thread = Thread(target=target, args=args, kwargs=kwargs, daemon=True)
    thread.start()
    return thread


class WorkflowService:
    """Application service for workflow API orchestration."""

    def __init__(
        self,
        *,
        repository: WorkflowRunRepository | None = None,
        runner: WorkflowRuntimeRunner | None = None,
        task_scheduler: Callable[..., Any] | None = None,
    ) -> None:
        self._repository = repository or WorkflowRunRepository()
        self._runner = runner or WorkflowRuntimeRunner(
            checkpointer=CheckpointerFactory().get_checkpointer()
        )
        self._task_scheduler = task_scheduler or default_task_scheduler

    def create_run(
        self,
        *,
        user_query: str,
        thread_id: str = "",
        title: str = "",
        enable_hitl_clarification: bool = False,
        enable_hitl_architecture_review: bool = False,
        runtime_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_thread_id = str(thread_id or "").strip() or self._generate_thread_id()
        attempt_id = generate_attempt_id()
        self._repository.create_or_get_thread(thread_id=normalized_thread_id, title=title)
        self._repository.create_attempt(
            thread_id=normalized_thread_id,
            attempt_id=attempt_id,
            user_query=user_query,
            title=title,
            runtime_metadata=runtime_metadata,
            enable_hitl_clarification=enable_hitl_clarification,
            enable_hitl_architecture_review=enable_hitl_architecture_review,
        )
        response = {
            "thread_id": normalized_thread_id,
            "attempt_id": attempt_id,
            "status": "queued",
            "poll_url": f"/api/workflow/threads/{normalized_thread_id}/attempts/{attempt_id}",
            "thread_url": f"/api/workflow/threads/{normalized_thread_id}",
        }
        self._task_scheduler(
            self._execute_run,
            normalized_thread_id,
            attempt_id,
            user_query,
            runtime_metadata or {},
            bool(enable_hitl_clarification),
            bool(enable_hitl_architecture_review),
        )
        return response

    def get_thread(self, thread_id: str) -> dict[str, Any]:
        thread = self._repository.get_thread(thread_id)
        if thread is None:
            raise NotFoundError(f"unknown thread: {thread_id}")
        latest_attempt = (
            self._repository.get_attempt(thread_id, thread.latest_attempt_id)
            if thread.latest_attempt_id
            else None
        )
        return build_thread_overview(thread, latest_attempt)

    def list_attempts(self, thread_id: str) -> dict[str, Any]:
        thread = self._repository.get_thread(thread_id)
        if thread is None:
            raise NotFoundError(f"unknown thread: {thread_id}")
        return {
            "thread_id": thread_id,
            "items": [build_attempt_list_item(item) for item in self._repository.list_attempts(thread_id)],
        }

    def get_attempt_detail(self, thread_id: str, attempt_id: str) -> dict[str, Any]:
        attempt = self._require_attempt(thread_id, attempt_id)
        state = self._current_state_for_attempt(attempt)
        return build_attempt_detail(attempt, state)

    def get_attempt_result(self, thread_id: str, attempt_id: str) -> dict[str, Any]:
        attempt = self._require_attempt(thread_id, attempt_id)
        state = self._current_state_for_attempt(attempt)
        return build_attempt_result(attempt, state)

    def resume_thread(
        self,
        *,
        thread_id: str,
        attempt_id: str,
        review_id: str,
        decision: str,
        answers: list[Any] | None,
        feedback: str,
        updated_constraints: dict[str, Any] | None,
    ) -> dict[str, Any]:
        attempt = self._require_attempt(thread_id, attempt_id)
        if attempt.status == "running":
            raise ConflictError("attempt is already running")

        state = self._current_state_for_attempt(attempt)
        current_review_id = str(
            (state.get("review_id", "") or (state.get("review_request", {}) or {}).get("review_id", "") or "")
        ).strip()
        current_review_stage = str(((state.get("review_request", {}) or {}).get("stage", "") or "")).strip()
        if infer_attempt_status(state, fallback=attempt.status) != "interrupted":
            raise ConflictError("当前线程没有待处理的 review，无法恢复执行。")
        if current_review_id != str(review_id or "").strip():
            raise ConflictError("review_id 不匹配，无法恢复执行。")

        normalized_payload = normalize_review_response(
            {
                "decision": decision,
                "answers": list(answers or []),
                "feedback": feedback,
                "updated_constraints": dict(updated_constraints or {}),
                "review_id": review_id,
            },
            review_id=current_review_id,
        )

        self._task_scheduler(
            self._execute_resume,
            thread_id,
            attempt_id,
            attempt.user_query,
            dict(attempt.runtime_metadata or {}),
            normalized_payload,
        )
        return {
            "thread_id": thread_id,
            "attempt_id": attempt_id,
            "status": "running",
            "message": f"review 已提交，工作流继续执行中。stage={current_review_stage or 'unknown'}",
        }

    def health(self) -> dict[str, Any]:
        runner_health = dict(self._runner.health_check())
        collections = self._check_chroma_collections()
        chroma_ready = all(collections.values())
        return {
            "ok": bool(runner_health.get("checkpointer_ready", False)),
            "llm_provider": config.LLM_PROVIDER,
            "embedding_provider": config.EMBEDDING_PROVIDER,
            "checkpointer_ready": bool(runner_health.get("checkpointer_ready", False)),
            "chroma_ready": chroma_ready,
            "collections": collections,
        }

    def _execute_run(
        self,
        thread_id: str,
        attempt_id: str,
        user_query: str,
        runtime_metadata: dict[str, Any],
        enable_hitl_clarification: bool,
        enable_hitl_architecture_review: bool,
    ) -> None:
        self._repository.mark_attempt_running(thread_id, attempt_id)
        try:
            result = self._runner.run(
                attempt_id=attempt_id,
                thread_id=thread_id,
                user_query=user_query,
                runtime_metadata=runtime_metadata,
                enable_hitl_clarification=enable_hitl_clarification,
                enable_hitl_architecture_review=enable_hitl_architecture_review,
            )
            status = infer_attempt_status(result.state, fallback="completed")
            self._repository.update_attempt_state(
                thread_id,
                attempt_id,
                status=status,
                state=result.state,
                trace_files=result.trace_files,
            )
        except Exception as exc:
            self._repository.mark_attempt_failed(
                thread_id,
                attempt_id,
                error_code=type(exc).__name__,
                error_message=str(exc),
            )

    def _execute_resume(
        self,
        thread_id: str,
        attempt_id: str,
        user_query: str,
        runtime_metadata: dict[str, Any],
        resume_payload: dict[str, Any],
    ) -> None:
        self._repository.mark_attempt_running(thread_id, attempt_id)
        try:
            result = self._runner.resume(
                attempt_id=attempt_id,
                thread_id=thread_id,
                user_query=user_query,
                resume_payload=resume_payload,
                runtime_metadata=runtime_metadata,
            )
            status = infer_attempt_status(result.state, fallback="completed")
            self._repository.update_attempt_state(
                thread_id,
                attempt_id,
                status=status,
                state=result.state,
                trace_files=result.trace_files,
            )
        except Exception as exc:
            self._repository.mark_attempt_failed(
                thread_id,
                attempt_id,
                error_code=type(exc).__name__,
                error_message=str(exc),
            )

    def _current_state_for_attempt(self, attempt: AttemptRecord) -> dict[str, Any]:
        if attempt.status == "running":
            try:
                snapshot = self._runner.get_state_snapshot(thread_id=attempt.thread_id)
                values = snapshot.get("values", {}) or {}
                if isinstance(values, dict) and values:
                    return dict(values)
            except Exception:
                pass
        return dict(attempt.latest_state or {})

    def _require_attempt(self, thread_id: str, attempt_id: str) -> AttemptRecord:
        attempt = self._repository.get_attempt(thread_id, attempt_id)
        if attempt is None:
            raise NotFoundError(f"unknown attempt: {thread_id}/{attempt_id}")
        return attempt

    @staticmethod
    def _generate_thread_id() -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"wf_{stamp}_{uuid4().hex[:8]}"

    @staticmethod
    def _check_chroma_collections() -> dict[str, bool]:
        client = chromadb.PersistentClient(path=str(config.CHROMA_PERSIST_DIR))
        def has_collection(name: str) -> bool:
            try:
                client.get_collection(name=name)
                return True
            except Exception:
                return False
        return {
            "atomic_modules": has_collection(config.CHROMA_COLLECTION_ATOMIC_MODULES),
            "subflow_templates": has_collection(config.CHROMA_COLLECTION_SUBFLOW_TEMPLATES),
            "system_patterns": has_collection(config.CHROMA_COLLECTION_SYSTEM_PATTERNS),
        }
