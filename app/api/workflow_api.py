from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.models import CreateRunRequest, ResumeReviewRequest
from app.services.workflow_service import ConflictError, NotFoundError, WorkflowService


def build_workflow_router(service: WorkflowService) -> APIRouter:
    router = APIRouter(prefix="/api/workflow", tags=["workflow"])

    def _translate_error(exc: Exception) -> HTTPException:
        if isinstance(exc, NotFoundError):
            return HTTPException(status_code=404, detail={"code": exc.code, "message": str(exc)})
        if isinstance(exc, ConflictError):
            return HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc)})
        return HTTPException(status_code=500, detail={"code": "internal_error", "message": str(exc)})

    @router.post("/runs")
    def create_run(payload: CreateRunRequest) -> dict:
        try:
            return service.create_run(**payload.model_dump())
        except Exception as exc:
            raise _translate_error(exc) from exc

    @router.get("/threads/{thread_id}")
    def get_thread(thread_id: str) -> dict:
        try:
            return service.get_thread(thread_id)
        except Exception as exc:
            raise _translate_error(exc) from exc

    @router.get("/threads/{thread_id}/attempts")
    def list_attempts(thread_id: str) -> dict:
        try:
            return service.list_attempts(thread_id)
        except Exception as exc:
            raise _translate_error(exc) from exc

    @router.get("/threads/{thread_id}/attempts/{attempt_id}")
    def get_attempt_detail(thread_id: str, attempt_id: str) -> dict:
        try:
            return service.get_attempt_detail(thread_id, attempt_id)
        except Exception as exc:
            raise _translate_error(exc) from exc

    @router.get("/threads/{thread_id}/attempts/{attempt_id}/result")
    def get_attempt_result(thread_id: str, attempt_id: str) -> dict:
        try:
            return service.get_attempt_result(thread_id, attempt_id)
        except Exception as exc:
            raise _translate_error(exc) from exc

    @router.post("/threads/{thread_id}/resume")
    def resume_thread(thread_id: str, payload: ResumeReviewRequest) -> dict:
        try:
            return service.resume_thread(thread_id=thread_id, **payload.model_dump())
        except Exception as exc:
            raise _translate_error(exc) from exc

    @router.get("/health")
    def health() -> dict:
        try:
            return service.health()
        except Exception as exc:
            raise _translate_error(exc) from exc

    return router
