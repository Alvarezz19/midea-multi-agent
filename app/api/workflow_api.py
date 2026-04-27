from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.api.models import CreateRunRequest, ResumeReviewRequest
from app.services.workflow_service import ConflictError, NotFoundError, WorkflowService, WorkflowServiceError


def build_error_response(exc: Exception) -> JSONResponse:
    if isinstance(exc, NotFoundError):
        status_code = 404
        code = exc.code
        details = exc.details
    elif isinstance(exc, ConflictError):
        status_code = 409
        code = exc.code
        details = exc.details
    elif isinstance(exc, WorkflowServiceError):
        status_code = 500
        code = exc.code
        details = exc.details
    else:
        status_code = 500
        code = "internal_error"
        details = {}
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder({"error": {"code": code, "message": str(exc), "details": details}}),
    )


def build_workflow_router(service: WorkflowService) -> APIRouter:
    router = APIRouter(prefix="/api/workflow", tags=["workflow"])

    @router.post("/runs")
    def create_run(payload: CreateRunRequest):
        try:
            return service.create_run(**payload.model_dump())
        except Exception as exc:
            return build_error_response(exc)

    @router.get("/threads/{thread_id}")
    def get_thread(thread_id: str):
        try:
            return service.get_thread(thread_id)
        except Exception as exc:
            return build_error_response(exc)

    @router.get("/threads/{thread_id}/attempts")
    def list_attempts(thread_id: str):
        try:
            return service.list_attempts(thread_id)
        except Exception as exc:
            return build_error_response(exc)

    @router.get("/threads/{thread_id}/attempts/{attempt_id}")
    def get_attempt_detail(thread_id: str, attempt_id: str):
        try:
            return service.get_attempt_detail(thread_id, attempt_id)
        except Exception as exc:
            return build_error_response(exc)

    @router.get("/threads/{thread_id}/attempts/{attempt_id}/result")
    def get_attempt_result(thread_id: str, attempt_id: str):
        try:
            return service.get_attempt_result(thread_id, attempt_id)
        except Exception as exc:
            return build_error_response(exc)

    @router.get("/threads/{thread_id}/attempts/{attempt_id}/trace")
    def get_attempt_trace(thread_id: str, attempt_id: str):
        try:
            return service.get_attempt_trace(thread_id, attempt_id)
        except Exception as exc:
            return build_error_response(exc)

    @router.get("/threads/{thread_id}/attempts/{attempt_id}/state-history")
    def get_attempt_state_history(thread_id: str, attempt_id: str, limit: int = Query(default=10, ge=1, le=100)):
        try:
            return service.get_attempt_state_history(thread_id, attempt_id, limit=limit)
        except Exception as exc:
            return build_error_response(exc)

    @router.post("/threads/{thread_id}/resume")
    def resume_thread(thread_id: str, payload: ResumeReviewRequest):
        try:
            return service.resume_thread(thread_id=thread_id, **payload.model_dump())
        except Exception as exc:
            return build_error_response(exc)

    @router.get("/health")
    def health():
        try:
            return service.health()
        except Exception as exc:
            return build_error_response(exc)

    return router
