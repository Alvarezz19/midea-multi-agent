from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any


ACTIVE_ATTEMPT_STATUSES = {"queued", "running", "interrupted"}
TERMINAL_ATTEMPT_STATUSES = {"completed", "rejected", "failed"}
ALLOWED_ATTEMPT_STATUSES = ACTIVE_ATTEMPT_STATUSES | TERMINAL_ATTEMPT_STATUSES


class ActiveAttemptExistsError(RuntimeError):
    def __init__(self, attempt_id: str, status: str) -> None:
        super().__init__(f"active attempt already exists: {attempt_id} ({status})")
        self.attempt_id = attempt_id
        self.status = status


class InvalidAttemptTransitionError(RuntimeError):
    pass


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_repository_path() -> Path:
    return Path(os.getenv("WORKFLOW_RUN_REPOSITORY_PATH", "outputs/workflow_api/runs.json"))


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
    """线程安全的 workflow thread / attempt 仓储。

    传入 storage_path 时会落盘为 JSON，满足本地联调阶段的重启恢复需求。
    """

    def __init__(self, *, storage_path: str | Path | None = None) -> None:
        self._lock = RLock()
        self._storage_path = Path(storage_path) if storage_path else None
        self._threads: dict[str, ThreadRecord] = {}
        self._attempts: dict[tuple[str, str], AttemptRecord] = {}
        if self._storage_path:
            self._load_from_disk()

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
                self._persist_locked()
            elif title and not record.title:
                record.title = title
                record.updated_at = utc_now_iso()
                self._persist_locked()
            return self._copy_thread(record)

    def get_thread(self, thread_id: str) -> ThreadRecord | None:
        with self._lock:
            record = self._threads.get(thread_id)
            return self._copy_thread(record) if record else None

    def get_active_attempt(self, thread_id: str) -> AttemptRecord | None:
        with self._lock:
            attempts = [
                record
                for (record_thread_id, _), record in self._attempts.items()
                if record_thread_id == thread_id and record.status in ACTIVE_ATTEMPT_STATUSES
            ]
            if not attempts:
                return None
            latest = sorted(attempts, key=lambda item: item.created_at, reverse=True)[0]
            return self._copy_attempt(latest)

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
        enforce_single_active: bool = False,
    ) -> AttemptRecord:
        with self._lock:
            if enforce_single_active:
                active_attempt = self.get_active_attempt(thread_id)
                if active_attempt is not None:
                    raise ActiveAttemptExistsError(active_attempt.attempt_id, active_attempt.status)

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
            self._persist_locked()
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
            if record.status not in {"queued", "interrupted"}:
                raise InvalidAttemptTransitionError(
                    f"attempt {attempt_id} cannot transition from {record.status} to running"
                )
            record.status = "running"
            record.finished_at = ""
            record.updated_at = utc_now_iso()
            self._sync_thread_latest(thread_id, attempt_id, "running")
            self._persist_locked()
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
            if status not in ALLOWED_ATTEMPT_STATUSES:
                raise InvalidAttemptTransitionError(f"unsupported attempt status: {status}")

            record = self._require_attempt(thread_id, attempt_id)
            record.status = status
            record.updated_at = utc_now_iso()
            if status in TERMINAL_ATTEMPT_STATUSES:
                record.finished_at = record.updated_at
            elif status == "interrupted":
                record.finished_at = ""
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
            self._persist_locked()
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

    def _load_from_disk(self) -> None:
        if self._storage_path is None or not self._storage_path.exists():
            return
        with self._storage_path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        self._threads = {
            item["thread_id"]: ThreadRecord(**item)
            for item in list(payload.get("threads", []) or [])
        }
        self._attempts = {}
        for item in list(payload.get("attempts", []) or []):
            record = AttemptRecord(**item)
            self._attempts[(record.thread_id, record.attempt_id)] = record

    def _persist_locked(self) -> None:
        if self._storage_path is None:
            return
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "workflow-api-repository-v1",
            "updated_at": utc_now_iso(),
            "threads": [asdict(record) for record in self._threads.values()],
            "attempts": [asdict(record) for record in self._attempts.values()],
        }
        tmp_path = self._storage_path.with_suffix(f"{self._storage_path.suffix}.tmp")
        with tmp_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
        tmp_path.replace(self._storage_path)

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
