from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class AttemptRecord:
    attempt_id: str
    thread_id: str
    user_query: str
    title: str
    status: str
    created_at: str
    updated_at: str
    current_step: str = "start"
    workflow_status: str = ""
    review_id: str = ""
    review_stage: str = "none"
    verification_status: str = ""
    final_route_decision: str = ""
    trace_files: dict[str, Any] = field(default_factory=dict)
    latest_state: dict[str, Any] = field(default_factory=dict)
    error_code: str = ""
    error_message: str = ""
    finished_at: str = ""
    runtime_metadata: dict[str, Any] = field(default_factory=dict)
    enable_hitl_clarification: bool = False
    enable_hitl_architecture_review: bool = False


@dataclass
class ThreadRecord:
    thread_id: str
    title: str
    created_at: str
    updated_at: str
    latest_attempt_id: str = ""
    latest_status: str = "queued"


class WorkflowRunRepository:
    """Thread-safe in-memory repository for workflow threads and attempts."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._threads: dict[str, ThreadRecord] = {}
        self._attempts: dict[tuple[str, str], AttemptRecord] = {}

    def create_or_get_thread(self, *, thread_id: str, title: str = "") -> ThreadRecord:
        with self._lock:
            record = self._threads.get(thread_id)
            if record is None:
                now = utc_now_iso()
                record = ThreadRecord(
                    thread_id=thread_id,
                    title=title,
                    created_at=now,
                    updated_at=now,
                )
                self._threads[thread_id] = record
            elif title and not record.title:
                record.title = title
                record.updated_at = utc_now_iso()
            return self._copy_thread(record)

    def get_thread(self, thread_id: str) -> ThreadRecord | None:
        with self._lock:
            record = self._threads.get(thread_id)
            return self._copy_thread(record) if record else None

    def create_attempt(
        self,
        *,
        thread_id: str,
        attempt_id: str,
        user_query: str,
        title: str,
        runtime_metadata: dict[str, Any] | None,
        enable_hitl_clarification: bool,
        enable_hitl_architecture_review: bool,
    ) -> AttemptRecord:
        with self._lock:
            now = utc_now_iso()
            record = AttemptRecord(
                attempt_id=attempt_id,
                thread_id=thread_id,
                user_query=user_query,
                title=title,
                status="queued",
                created_at=now,
                updated_at=now,
                runtime_metadata=dict(runtime_metadata or {}),
                enable_hitl_clarification=bool(enable_hitl_clarification),
                enable_hitl_architecture_review=bool(enable_hitl_architecture_review),
            )
            self._attempts[(thread_id, attempt_id)] = record
            thread = self._threads[thread_id]
            thread.latest_attempt_id = attempt_id
            thread.latest_status = "queued"
            thread.updated_at = now
            return self._copy_attempt(record)

    def get_attempt(self, thread_id: str, attempt_id: str) -> AttemptRecord | None:
        with self._lock:
            record = self._attempts.get((thread_id, attempt_id))
            return self._copy_attempt(record) if record else None

    def list_attempts(self, thread_id: str) -> list[AttemptRecord]:
        with self._lock:
            attempts = [
                self._copy_attempt(record)
                for (record_thread_id, _), record in self._attempts.items()
                if record_thread_id == thread_id
            ]
        return sorted(attempts, key=lambda item: item.created_at, reverse=True)

    def mark_attempt_running(self, thread_id: str, attempt_id: str) -> AttemptRecord:
        with self._lock:
            record = self._require_attempt(thread_id, attempt_id)
            record.status = "running"
            record.updated_at = utc_now_iso()
            self._sync_thread_latest(thread_id, attempt_id, "running")
            return self._copy_attempt(record)

    def update_attempt_state(
        self,
        thread_id: str,
        attempt_id: str,
        *,
        status: str,
        state: dict[str, Any],
        trace_files: dict[str, Any] | None,
        error_code: str = "",
        error_message: str = "",
    ) -> AttemptRecord:
        with self._lock:
            record = self._require_attempt(thread_id, attempt_id)
            record.status = status
            record.updated_at = utc_now_iso()
            if status in {"completed", "interrupted", "rejected", "failed"}:
                record.finished_at = record.updated_at
            record.latest_state = dict(state or {})
            record.trace_files = dict(trace_files or {})
            record.error_code = error_code
            record.error_message = error_message
            record.current_step = str((state or {}).get("current_step", "") or record.current_step).strip()
            review_request = (state or {}).get("review_request", {}) or {}
            record.review_id = str(
                (state or {}).get("review_id", "")
                or review_request.get("review_id", "")
                or ""
            ).strip()
            record.review_stage = str(
                review_request.get("stage", "")
                or (state or {}).get("hitl_stage", "")
                or "none"
            ).strip() or "none"
            verification_report = (state or {}).get("verification_report", {}) or {}
            route_decision = (state or {}).get("route_decision", {}) or {}
            record.workflow_status = str((state or {}).get("workflow_status", "") or "").strip()
            record.verification_status = str(verification_report.get("status", "") or "").strip()
            record.final_route_decision = str(route_decision.get("decision", "") or "").strip()
            self._sync_thread_latest(thread_id, attempt_id, status)
            return self._copy_attempt(record)

    def mark_attempt_failed(
        self,
        thread_id: str,
        attempt_id: str,
        *,
        error_code: str,
        error_message: str,
    ) -> AttemptRecord:
        return self.update_attempt_state(
            thread_id,
            attempt_id,
            status="failed",
            state={},
            trace_files={},
            error_code=error_code,
            error_message=error_message,
        )

    def _sync_thread_latest(self, thread_id: str, attempt_id: str, status: str) -> None:
        thread = self._threads[thread_id]
        thread.latest_attempt_id = attempt_id
        thread.latest_status = status
        thread.updated_at = utc_now_iso()

    def _require_attempt(self, thread_id: str, attempt_id: str) -> AttemptRecord:
        record = self._attempts.get((thread_id, attempt_id))
        if record is None:
            raise KeyError(f"unknown attempt: {thread_id}/{attempt_id}")
        return record

    @staticmethod
    def _copy_thread(record: ThreadRecord | None) -> ThreadRecord | None:
        if record is None:
            return None
        return ThreadRecord(**record.__dict__)

    @staticmethod
    def _copy_attempt(record: AttemptRecord | None) -> AttemptRecord | None:
        if record is None:
            return None
        return AttemptRecord(
            attempt_id=record.attempt_id,
            thread_id=record.thread_id,
            user_query=record.user_query,
            title=record.title,
            status=record.status,
            created_at=record.created_at,
            updated_at=record.updated_at,
            current_step=record.current_step,
            workflow_status=record.workflow_status,
            review_id=record.review_id,
            review_stage=record.review_stage,
            verification_status=record.verification_status,
            final_route_decision=record.final_route_decision,
            trace_files=dict(record.trace_files),
            latest_state=dict(record.latest_state),
            error_code=record.error_code,
            error_message=record.error_message,
            finished_at=record.finished_at,
            runtime_metadata=dict(record.runtime_metadata),
            enable_hitl_clarification=record.enable_hitl_clarification,
            enable_hitl_architecture_review=record.enable_hitl_architecture_review,
        )
