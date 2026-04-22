from __future__ import annotations

from fastapi import FastAPI

from app.api.workflow_api import build_workflow_router
from app.services.workflow_service import WorkflowService


def create_app(service: WorkflowService | None = None) -> FastAPI:
    workflow_service = service or WorkflowService()
    app = FastAPI(title="Midea Workflow API", version="0.1.0")
    app.include_router(build_workflow_router(workflow_service))
    app.state.workflow_service = workflow_service
    return app


app = create_app()
