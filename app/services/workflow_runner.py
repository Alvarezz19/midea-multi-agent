from __future__ import annotations

from dataclasses import dataclass
from time import time
from typing import Any

from langgraph.types import Command

import workflow
import workflow_trace
from utils.trace_index import generate_attempt_id
from utils.workflow_runtime import build_runtime_invoke_config, build_configurable_thread, compile_state_graph


def _snapshot_to_dict(snapshot: Any) -> dict[str, Any]:
    if snapshot is None:
        return {}
    return {
        "next": list(getattr(snapshot, "next", ()) or ()),
        "values": getattr(snapshot, "values", {}) or {},
        "config": getattr(snapshot, "config", {}) or {},
        "metadata": getattr(snapshot, "metadata", {}) or {},
        "created_at": str(getattr(snapshot, "created_at", "") or ""),
    }


@dataclass
class WorkflowRunResult:
    state: dict[str, Any]
    trace_files: dict[str, Any]


class WorkflowRuntimeRunner:
    """Bridge between the HTTP service layer and the LangGraph runtime."""

    def __init__(self, *, checkpointer: Any) -> None:
        self._checkpointer = checkpointer

    def run(
        self,
        *,
        attempt_id: str,
        thread_id: str,
        user_query: str,
        runtime_metadata: dict[str, Any] | None,
        enable_hitl_clarification: bool,
        enable_hitl_architecture_review: bool,
        enable_repair_agent: bool = False,
    ) -> WorkflowRunResult:
        node_io_records: list[dict[str, Any]] = []
        started_at = time()
        app = self._compile_trace_app(node_io_records)
        initial_state = workflow.build_initial_state(
            user_query,
            enable_hitl_clarification=bool(enable_hitl_clarification and str(thread_id or "").strip()),
            enable_hitl_architecture_review=bool(enable_hitl_architecture_review and str(thread_id or "").strip()),
            enable_repair_agent=enable_repair_agent,
        )
        invoke_config = build_runtime_invoke_config(
            user_query=user_query,
            run_name="MideaWorkflowApi",
            tags=["workflow", "langgraph", "api"],
            recursion_limit=workflow.PHASE4_RECURSION_LIMIT,
            thread_id=thread_id,
            checkpointer=self._checkpointer,
            extra_metadata=runtime_metadata,
        )
        invoke_config.setdefault("metadata", {})
        invoke_config["metadata"]["attempt_id"] = attempt_id or generate_attempt_id()

        result: dict[str, Any] | None = None
        try:
            result = app.invoke(initial_state, config=invoke_config)
        finally:
            final_state = result if result is not None else self._best_effort_state(app, thread_id, fallback=initial_state)
            trace_files = workflow_trace._save_workflow_trace(
                user_query=user_query,
                node_io_records=node_io_records,
                final_state=final_state,
                total_elapsed_seconds=time() - started_at,
                thread_id=thread_id,
                attempt_id=attempt_id,
            )
            final_state.setdefault("final_output", {})
            final_state["final_output"]["workflow_trace"] = trace_files
        return WorkflowRunResult(state=final_state, trace_files=trace_files)

    def resume(
        self,
        *,
        attempt_id: str,
        thread_id: str,
        user_query: str,
        resume_payload: dict[str, Any],
        runtime_metadata: dict[str, Any] | None,
    ) -> WorkflowRunResult:
        node_io_records: list[dict[str, Any]] = []
        started_at = time()
        app = self._compile_trace_app(node_io_records)
        invoke_config = build_runtime_invoke_config(
            user_query=user_query,
            run_name="MideaWorkflowApiResume",
            tags=["workflow", "langgraph", "api", "resume"],
            recursion_limit=workflow.PHASE4_RECURSION_LIMIT,
            thread_id=thread_id,
            checkpointer=self._checkpointer,
            extra_metadata=runtime_metadata,
        )
        invoke_config.setdefault("metadata", {})
        invoke_config["metadata"]["attempt_id"] = attempt_id or generate_attempt_id()

        result: dict[str, Any] | None = None
        try:
            result = app.invoke(Command(resume=resume_payload), config=invoke_config)
        finally:
            final_state = result if result is not None else self._best_effort_state(app, thread_id, fallback={})
            trace_files = workflow_trace._save_workflow_trace(
                user_query=user_query,
                node_io_records=node_io_records,
                final_state=final_state,
                total_elapsed_seconds=time() - started_at,
                thread_id=thread_id,
                attempt_id=attempt_id,
            )
            final_state.setdefault("final_output", {})
            final_state["final_output"]["workflow_trace"] = trace_files
        return WorkflowRunResult(state=final_state, trace_files=trace_files)

    def get_state_snapshot(self, *, thread_id: str) -> dict[str, Any]:
        app = self._compile_formal_app()
        snapshot = app.get_state({"configurable": build_configurable_thread(thread_id)})
        return _snapshot_to_dict(snapshot)

    def get_state_history(self, *, thread_id: str, limit: int = 10) -> list[dict[str, Any]]:
        app = self._compile_formal_app()
        snapshots = app.get_state_history({"configurable": build_configurable_thread(thread_id)})
        return [_snapshot_to_dict(snapshot) for snapshot in list(snapshots)[:limit]]

    def health_check(self) -> dict[str, Any]:
        return {"checkpointer_ready": self._checkpointer is not None}

    def _compile_trace_app(self, node_io_records: list[dict[str, Any]]) -> Any:
        state_graph = workflow_trace.create_workflow(
            checkpointer=self._checkpointer,
            node_io_records=node_io_records,
        )
        return compile_state_graph(state_graph, checkpointer=self._checkpointer)

    def _compile_formal_app(self) -> Any:
        state_graph = workflow.create_workflow(checkpointer=self._checkpointer)
        return compile_state_graph(state_graph, checkpointer=self._checkpointer)

    def _best_effort_state(self, app: Any, thread_id: str, *, fallback: dict[str, Any]) -> dict[str, Any]:
        try:
            snapshot = app.get_state({"configurable": build_configurable_thread(thread_id)})
            values = getattr(snapshot, "values", {}) or {}
            if isinstance(values, dict):
                return dict(values)
        except Exception:
            pass
        return dict(fallback or {})
