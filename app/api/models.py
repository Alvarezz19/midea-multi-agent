from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class CreateRunRequest(BaseModel):
    user_query: str = Field(min_length=1)
    thread_id: str = ""
    title: str = ""
    enable_hitl_clarification: bool = False
    enable_hitl_architecture_review: bool = False
    runtime_metadata: dict[str, Any] = Field(default_factory=dict)


class ResumeReviewRequest(BaseModel):
    attempt_id: str = Field(min_length=1)
    review_id: str = Field(min_length=1)
    decision: Literal["approve", "feedback", "clarify", "reject"]
    answers: list[Any] = Field(default_factory=list)
    feedback: str = ""
    updated_constraints: dict[str, Any] = Field(default_factory=dict)


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorBody
