import type { ReviewDecision, ResumeReviewRequest } from "../../../types/workflow";

const DECISIONS: ReviewDecision[] = ["approve", "feedback", "clarify", "reject"];

export interface ReviewDraft {
  attemptId: string;
  reviewId: string;
  decision: string;
  answersText: string;
  feedback: string;
  updatedConstraintsText: string;
}

export interface ReviewValidationResult {
  valid: boolean;
  payload?: ResumeReviewRequest;
  message?: string;
}

function parseJsonObject(text: string): Record<string, unknown> | null {
  const normalized = text.trim();
  if (!normalized) {
    return {};
  }
  const value = JSON.parse(normalized);
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

export function validateReviewDraft(draft: ReviewDraft): ReviewValidationResult {
  if (!draft.attemptId.trim() || !draft.reviewId.trim()) {
    return { valid: false, message: "缺少 attempt_id 或 review_id。" };
  }
  if (!DECISIONS.includes(draft.decision as ReviewDecision)) {
    return { valid: false, message: "请选择合法的 review 决策。" };
  }
  if ((draft.decision === "feedback" || draft.decision === "clarify") && !draft.feedback.trim()) {
    return { valid: false, message: "feedback / clarify 需要填写反馈说明。" };
  }

  let updatedConstraints: Record<string, unknown> | null = {};
  try {
    updatedConstraints = parseJsonObject(draft.updatedConstraintsText);
  } catch {
    return { valid: false, message: "updated_constraints 必须是合法 JSON 对象。" };
  }
  if (updatedConstraints === null) {
    return { valid: false, message: "updated_constraints 必须是 JSON 对象，不能是数组或基础值。" };
  }

  const answers = draft.answersText
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);

  return {
    valid: true,
    payload: {
      attempt_id: draft.attemptId,
      review_id: draft.reviewId,
      decision: draft.decision as ReviewDecision,
      answers,
      feedback: draft.feedback.trim(),
      updated_constraints: updatedConstraints
    }
  };
}
