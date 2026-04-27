from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver


class CheckpointerFactory:
    """统一创建 LangGraph checkpointer。

    默认使用 SQLite，`memory` 只用于单测或临时 demo。
    """

    def __init__(
        self,
        checkpointer: Any | None = None,
        *,
        backend: str | None = None,
        sqlite_path: str | Path | None = None,
    ) -> None:
        self._provided_checkpointer = checkpointer
        self._backend = str(backend or os.getenv("WORKFLOW_CHECKPOINTER_BACKEND", "sqlite")).strip().lower()
        self._sqlite_path = Path(
            sqlite_path or os.getenv("WORKFLOW_CHECKPOINT_DB_PATH", "outputs/workflow_api/checkpoints.sqlite3")
        )
        self._checkpointer: Any | None = None
        self._sqlite_connection: sqlite3.Connection | None = None

    def get_checkpointer(self) -> Any:
        if self._checkpointer is not None:
            return self._checkpointer
        if self._provided_checkpointer is not None:
            self._checkpointer = self._provided_checkpointer
            return self._checkpointer
        if self._backend == "memory":
            self._checkpointer = InMemorySaver()
            return self._checkpointer
        if self._backend == "sqlite":
            self._sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            self._sqlite_connection = sqlite3.connect(str(self._sqlite_path), check_same_thread=False)
            self._checkpointer = SqliteSaver(self._sqlite_connection)
            if hasattr(self._checkpointer, "setup"):
                self._checkpointer.setup()
            return self._checkpointer
        raise ValueError(f"unsupported workflow checkpointer backend: {self._backend}")

    def health_check(self) -> dict[str, Any]:
        checkpointer = self.get_checkpointer()
        sqlite_writable = True
        if self._backend == "sqlite":
            try:
                self._sqlite_path.parent.mkdir(parents=True, exist_ok=True)
                probe = self._sqlite_path.parent / ".workflow_checkpointer_write_test"
                probe.write_text("ok", encoding="utf-8")
                probe.unlink(missing_ok=True)
            except Exception:
                sqlite_writable = False
        return {
            "checkpointer_backend": self._backend,
            "checkpointer_ready": checkpointer is not None and sqlite_writable,
            "checkpoint_db_path": str(self._sqlite_path) if self._backend == "sqlite" else "",
        }
