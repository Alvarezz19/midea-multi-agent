import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { AttemptDetail } from "../../../types/workflow";
import { ReviewCard } from "./ReviewCard";

const interruptedAttempt: AttemptDetail = {
  thread_id: "thread-1",
  attempt_id: "attempt-1",
  status: "interrupted",
  current_step: "architecture_review_prepared",
  workflow_status: "interrupted",
  user_query: "为 AHU 生成控制骨架",
  review: {
    review_id: "review-1",
    stage: "architecture_review",
    status: "pending",
    question: "请确认结构骨架。",
    options: [
      { label: "批准继续", value: "approve", description: "继续" },
      { label: "反馈后重规划", value: "feedback", description: "反馈" }
    ],
    context_summary: "页面列表：控制"
  },
  progress: {
    current_step_label: "architecture_review_prepared",
    last_successful_node: "architecture_planning",
    node_count: 6
  },
  diagnostics: {
    verification_status: "",
    verification_issue_summary: "",
    repair_round_count: 0,
    retry_counts_by_scope: {}
  },
  subtasks: []
};

describe("ReviewCard", () => {
  it("非 pending review 不显示提交入口", () => {
    render(
      <ReviewCard
        attempt={{ ...interruptedAttempt, status: "running" }}
        isSubmitting={false}
        submitError={null}
        onSubmit={vi.fn()}
      />
    );

    expect(screen.getByText("暂无待处理评审")).toBeInTheDocument();
  });

  it("feedback 未填写说明时阻止提交", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<ReviewCard attempt={interruptedAttempt} isSubmitting={false} submitError={null} onSubmit={onSubmit} />);

    await user.click(screen.getByLabelText(/反馈后重规划/));
    await user.click(screen.getByRole("button", { name: "提交 review 并恢复执行" }));

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText(/需要填写反馈说明/)).toBeInTheDocument();
  });

  it("提交 approve 时携带 attempt_id 和 review_id", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<ReviewCard attempt={interruptedAttempt} isSubmitting={false} submitError={null} onSubmit={onSubmit} />);

    await user.click(screen.getByRole("button", { name: "提交 review 并恢复执行" }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        attempt_id: "attempt-1",
        review_id: "review-1",
        decision: "approve"
      })
    );
  });
});
