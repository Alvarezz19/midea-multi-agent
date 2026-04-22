from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import InMemorySaver


class CheckpointerFactory:
    """Temporary checkpointer factory.

    Current implementation uses a process-local in-memory saver so the API can
    support pause/resume in a single service process. Replace this with a
    durable backend before production rollout.
    """

    def __init__(self, checkpointer: Any | None = None) -> None:
        self._checkpointer = checkpointer or InMemorySaver()

    def get_checkpointer(self) -> Any:
        return self._checkpointer
