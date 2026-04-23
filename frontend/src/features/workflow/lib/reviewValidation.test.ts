import { describe, expect, it } from "vitest";

import { validateReviewDraft } from "./reviewValidation";

describe("reviewValidation", () => {
  it("生成和后端一致的 resume payload", () => {
    const result = validateReviewDraft({
      attemptId: "attempt-1",
      reviewId: "review-1",
      decision: "approve",
      answersText: "答案 A\n答案 B",
      feedback: "",
      updatedConstraintsText: "{\"required_pages\":[\"控制\"]}"
    });

    expect(result.valid).toBe(true);
    expect(result.payload).toEqual({
      attempt_id: "attempt-1",
      review_id: "review-1",
      decision: "approve",
      answers: ["答案 A", "答案 B"],
      feedback: "",
      updated_constraints: { required_pages: ["控制"] }
    });
  });

  it("feedback 和 clarify 必须填写说明", () => {
    const result = validateReviewDraft({
      attemptId: "attempt-1",
      reviewId: "review-1",
      decision: "feedback",
      answersText: "",
      feedback: "",
      updatedConstraintsText: "{}"
    });

    expect(result.valid).toBe(false);
    expect(result.message).toContain("需要填写反馈说明");
  });

  it("拒绝非法 updated_constraints JSON", () => {
    const result = validateReviewDraft({
      attemptId: "attempt-1",
      reviewId: "review-1",
      decision: "approve",
      answersText: "",
      feedback: "",
      updatedConstraintsText: "[]"
    });

    expect(result.valid).toBe(false);
    expect(result.message).toContain("JSON 对象");
  });
});
