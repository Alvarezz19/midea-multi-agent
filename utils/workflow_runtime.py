from __future__ import annotations

from typing import Any, Iterable


def build_configurable_thread(thread_id: str | None) -> dict[str, str]:
    normalized = str(thread_id or "").strip()
    if not normalized:
        raise ValueError("启用 checkpointer 时必须显式提供 thread_id。")
    return {"thread_id": normalized}


def build_runtime_invoke_config(
    *,
    user_query: str,
    run_name: str,
    tags: Iterable[str],
    recursion_limit: int,
    thread_id: str | None = None,
    checkpointer: Any | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_thread_id = str(thread_id or "").strip()

    metadata: dict[str, Any] = {"user_query": user_query}
    if extra_metadata:
        metadata.update(dict(extra_metadata))
    if normalized_thread_id:
        metadata["thread_id"] = normalized_thread_id
    metadata["persistence_enabled"] = bool(checkpointer is not None)

    config: dict[str, Any] = {
        "run_name": run_name,
        "tags": list(tags),
        "metadata": metadata,
        "recursion_limit": recursion_limit,
    }
    if checkpointer is not None:
        config["configurable"] = build_configurable_thread(normalized_thread_id)
    return config


def compile_state_graph(workflow: Any, *, checkpointer: Any | None = None) -> Any:
    if checkpointer is None:
        return workflow.compile()
    return workflow.compile(checkpointer=checkpointer)
