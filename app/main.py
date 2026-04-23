from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.workflow_api import build_workflow_router
from app.services.workflow_service import WorkflowService


def _workflow_cors_origins() -> list[str]:
    raw = os.getenv("WORKFLOW_CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173")
    return [item.strip() for item in raw.split(",") if item.strip()]


def create_app(service: WorkflowService | None = None) -> FastAPI:
    workflow_service = service or WorkflowService()
    app = FastAPI(title="Midea Workflow API", version="0.1.0")
    cors_origins = _workflow_cors_origins()
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

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
