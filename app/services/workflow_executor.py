from __future__ import annotations

from threading import Thread
from typing import Any, Callable, Protocol


class WorkflowTaskExecutor(Protocol):
    def submit(self, target: Callable[..., None], *args: Any, **kwargs: Any) -> Any:
        ...

    def health_check(self) -> dict[str, Any]:
        ...


class LocalThreadWorkflowExecutor:
    """本地线程执行器，适合开发联调和单进程部署。"""

    def submit(self, target: Callable[..., None], *args: Any, **kwargs: Any) -> Thread:
        thread = Thread(target=target, args=args, kwargs=kwargs, daemon=True)
        thread.start()
        return thread

    def health_check(self) -> dict[str, Any]:
        return {"worker_ready": True, "worker_backend": "local_thread"}


class InlineWorkflowExecutor:
    """同步执行器，只用于单元测试。"""

    def submit(self, target: Callable[..., None], *args: Any, **kwargs: Any) -> None:
        target(*args, **kwargs)
        return None

    def health_check(self) -> dict[str, Any]:
        return {"worker_ready": True, "worker_backend": "inline"}


class CallableWorkflowExecutor:
    """兼容旧的 task_scheduler 注入方式。"""

    def __init__(self, scheduler: Callable[..., Any]) -> None:
        self._scheduler = scheduler

    def submit(self, target: Callable[..., None], *args: Any, **kwargs: Any) -> Any:
        return self._scheduler(target, *args, **kwargs)

    def health_check(self) -> dict[str, Any]:
        return {"worker_ready": True, "worker_backend": "callable"}
