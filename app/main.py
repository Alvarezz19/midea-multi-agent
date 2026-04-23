from __future__ import annotations

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.api.workflow_api import build_workflow_router
from app.services.workflow_service import WorkflowService


def create_app(service: WorkflowService | None = None) -> FastAPI:
    workflow_service = service or WorkflowService()
    app = FastAPI(title="Midea Workflow API", version="0.1.0")

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "请求参数不符合接口约束。",
                    "details": {"errors": jsonable_encoder(exc.errors())},
                }
            },
        )

    app.include_router(build_workflow_router(workflow_service))
    app.state.workflow_service = workflow_service
    return app


app = create_app()
