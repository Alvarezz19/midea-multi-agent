from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

import chromadb

import config
import workflow_trace
from app.repositories.workflow_run_repository import (
    ACTIVE_ATTEMPT_STATUSES,
    TERMINAL_ATTEMPT_STATUSES,
    ActiveAttemptExistsError,
    AttemptRecord,
    WorkflowRunRepository,
    default_repository_path,
)
from app.services.checkpointer_factory import CheckpointerFactory
from app.services.workflow_executor import CallableWorkflowExecutor, LocalThreadWorkflowExecutor, WorkflowTaskExecutor
from app.services.workflow_runner import WorkflowRuntimeRunner
from app.services.workflow_state_projection import (
    build_attempt_detail,
    build_attempt_list_item,
    build_attempt_result,
    build_state_history_projection,
    build_thread_overview,
    build_trace_projection,
    infer_attempt_status,
)
from utils.phase3_contracts import normalize_review_response
from utils.trace_index import generate_attempt_id


class WorkflowServiceError(Exception):
    code = "workflow_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = dict(details or {})


class NotFoundError(WorkflowServiceError):
    code = "not_found"


class ConflictError(WorkflowServiceError):
    code = "conflict"


class DependencyUnavailableError(WorkflowServiceError):
    code = "dependency_unavailable"


class WorkflowService:
    """workflow API 的应用服务层。"""

    def __init__(
        self,
        *,
        repository: WorkflowRunRepository | None = None,
        runner: WorkflowRuntimeRunner | None = None,
        checkpointer_factory: CheckpointerFactory | None = None,
        task_executor: WorkflowTaskExecutor | None = None,
        task_scheduler: Callable[..., Any] | None = None,
    ) -> None:
        self._repository = repository or WorkflowRunRepository(storage_path=default_repository_path())
        self._checkpointer_factory = checkpointer_factory or CheckpointerFactory()
        self._runner = runner or WorkflowRuntimeRunner(
            checkpointer=self._checkpointer_factory.get_checkpointer()
        )
        if task_executor is not None:
            self._task_executor = task_executor
        elif task_scheduler is not None:
            self._task_executor = CallableWorkflowExecutor(task_scheduler)
        else:
            self._task_executor = LocalThreadWorkflowExecutor()

    def create_run(
        self,
        *,
        user_query: str,
        thread_id: str = "",
        title: str = "",
        enable_hitl_clarification: bool = False,
        enable_hitl_architecture_review: bool = False,
        enable_repair_agent: bool = False,
        runtime_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_thread_id = str(thread_id or "").strip() or self._generate_thread_id()
        attempt_id = generate_attempt_id()
        self._repository.create_or_get_thread(thread_id=normalized_thread_id, title=title)
        try:
            self._repository.create_attempt(
                thread_id=normalized_thread_id,
                attempt_id=attempt_id,
                user_query=user_query,
                title=title,
                runtime_metadata=runtime_metadata,
                enable_hitl_clarification=enable_hitl_clarification,
                enable_hitl_architecture_review=enable_hitl_architecture_review,
                enable_repair_agent=enable_repair_agent,
                enforce_single_active=True,
            )
        except ActiveAttemptExistsError as exc:
            raise ConflictError(
                "当前 thread 已存在 active attempt，请等待完成或恢复当前 review。",
                details={
                    "thread_id": normalized_thread_id,
                    "active_attempt_id": exc.attempt_id,
                    "active_status": exc.status,
                },
            ) from exc
        response = {
            "thread_id": normalized_thread_id,
            "attempt_id": attempt_id,
            "status": "queued",
            "poll_url": f"/api/workflow/threads/{normalized_thread_id}/attempts/{attempt_id}",
            "thread_url": f"/api/workflow/threads/{normalized_thread_id}",
        }
        self._task_executor.submit(
            self._execute_run,
            normalized_thread_id,
            attempt_id,
            user_query,
            runtime_metadata or {},
            bool(enable_hitl_clarification),
            bool(enable_hitl_architecture_review),
            bool(enable_repair_agent),
        )
        return response

    def get_thread(self, thread_id: str) -> dict[str, Any]:
        thread = self._repository.get_thread(thread_id)
        if thread is None:
            raise NotFoundError("thread 不存在。", details={"thread_id": thread_id})
        latest_attempt = (
            self._repository.get_attempt(thread_id, thread.latest_attempt_id)
            if thread.latest_attempt_id
            else None
        )
        return build_thread_overview(thread, latest_attempt)

    def list_attempts(self, thread_id: str) -> dict[str, Any]:
        thread = self._repository.get_thread(thread_id)
        if thread is None:
            raise NotFoundError("thread 不存在。", details={"thread_id": thread_id})
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

    def get_attempt_trace(self, thread_id: str, attempt_id: str) -> dict[str, Any]:
        attempt = self._require_attempt(thread_id, attempt_id)
        state = self._current_state_for_attempt(attempt)
        trace_files = dict(((state.get("final_output", {}) or {}).get("workflow_trace", {}) or {}) or attempt.trace_files)
        trace_summary = self._load_trace_summary(trace_files)
        return build_trace_projection(attempt, state, trace_summary)

    def get_attempt_state_history(self, thread_id: str, attempt_id: str, *, limit: int = 10) -> dict[str, Any]:
        self._require_attempt(thread_id, attempt_id)
        snapshots = self._runner.get_state_history(thread_id=thread_id, limit=limit)
        return build_state_history_projection(thread_id=thread_id, attempt_id=attempt_id, snapshots=snapshots)

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
        thread = self._repository.get_thread(thread_id)
        if thread is None:
            raise NotFoundError("thread 不存在。", details={"thread_id": thread_id})

        active_attempt = self._repository.get_active_attempt(thread_id)
        target_attempt = self._repository.get_attempt(thread_id, attempt_id)
        if active_attempt is None:
            if target_attempt and target_attempt.status in TERMINAL_ATTEMPT_STATUSES:
                raise ConflictError(
                    "终态 attempt 不允许再次 resume。",
                    details={"thread_id": thread_id, "attempt_id": attempt_id, "status": target_attempt.status},
                )
            raise ConflictError(
                "当前线程没有 active interrupted attempt，无法恢复执行。",
                details={"thread_id": thread_id, "attempt_id": attempt_id},
            )
        if active_attempt.attempt_id != attempt_id:
            raise ConflictError(
                "attempt_id 不匹配，resume 只能恢复当前 active attempt。",
                details={
                    "thread_id": thread_id,
                    "attempt_id": attempt_id,
                    "active_attempt_id": active_attempt.attempt_id,
                    "active_status": active_attempt.status,
                },
            )
        if active_attempt.status != "interrupted":
            raise ConflictError(
                "当前 active attempt 尚未处于 interrupted 状态，无法 resume。",
                details={"thread_id": thread_id, "attempt_id": attempt_id, "status": active_attempt.status},
            )

        state = self._current_state_for_attempt(active_attempt)
        current_review_id = str(
            (state.get("review_id", "") or (state.get("review_request", {}) or {}).get("review_id", "") or "")
        ).strip()
        current_review_stage = str(((state.get("review_request", {}) or {}).get("stage", "") or "")).strip()
        if infer_attempt_status(state, fallback=active_attempt.status) != "interrupted":
            raise ConflictError(
                "当前线程没有待处理的 review，无法恢复执行。",
                details={"thread_id": thread_id, "attempt_id": attempt_id},
            )
        if current_review_id != str(review_id or "").strip():
            raise ConflictError(
                "review_id 不匹配，无法恢复执行。",
                details={
                    "thread_id": thread_id,
                    "attempt_id": attempt_id,
                    "review_id": review_id,
                    "active_review_id": current_review_id,
                },
            )

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

        self._task_executor.submit(
            self._execute_resume,
            thread_id,
            attempt_id,
            active_attempt.user_query,
            dict(active_attempt.runtime_metadata or {}),
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
        checkpointer_health = self._checkpointer_factory.health_check()
        worker_health = self._task_executor.health_check()
        collections = self._check_chroma_collections()
        chroma_ready = all(collections.values())
        trace_writable = self._check_trace_root_writable()
        ok = bool(
            runner_health.get("checkpointer_ready", False)
            and checkpointer_health.get("checkpointer_ready", False)
            and worker_health.get("worker_ready", False)
            and trace_writable
        )
        return {
            "ok": ok,
            "llm_provider": config.LLM_PROVIDER,
            "embedding_provider": config.EMBEDDING_PROVIDER,
            "checkpointer_ready": bool(checkpointer_health.get("checkpointer_ready", False)),
            "checkpointer_backend": checkpointer_health.get("checkpointer_backend", ""),
            "checkpoint_db_path": checkpointer_health.get("checkpoint_db_path", ""),
            "worker_ready": bool(worker_health.get("worker_ready", False)),
            "worker_backend": worker_health.get("worker_backend", ""),
            "trace_root_writable": trace_writable,
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
        enable_repair_agent: bool,
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
                enable_repair_agent=enable_repair_agent,
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
        if attempt.status in ACTIVE_ATTEMPT_STATUSES:
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
            raise NotFoundError(
                "attempt 不存在。",
                details={"thread_id": thread_id, "attempt_id": attempt_id},
            )
        return attempt

    @staticmethod
    def _generate_thread_id() -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"wf_{stamp}_{uuid4().hex[:8]}"

    @staticmethod
    def _load_trace_summary(trace_files: dict[str, Any]) -> dict[str, Any]:
        summary_json = str(trace_files.get("summary_json", "") or "").strip()
        if not summary_json:
            return {}
        path = Path(summary_json)
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        if isinstance(payload, dict):
            return payload
        return {}

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

    @staticmethod
    def _check_trace_root_writable() -> bool:
        try:
            root = Path(workflow_trace.TRACE_OUTPUT_ROOT)
            root.mkdir(parents=True, exist_ok=True)
            probe = root / ".workflow_trace_write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return True
        except Exception:
            return False
