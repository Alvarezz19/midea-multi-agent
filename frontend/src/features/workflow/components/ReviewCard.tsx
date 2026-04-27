import { FormEvent, useMemo, useState } from "react";

import type { AttemptDetail, ReviewDecision, ResumeReviewRequest } from "../../../types/workflow";
import { validateReviewDraft } from "../lib/reviewValidation";

interface ReviewCardProps {
  attempt: AttemptDetail;
  isSubmitting: boolean;
  submitError: unknown;
  onSubmit: (payload: ResumeReviewRequest) => Promise<void>;
}

const FALLBACK_OPTIONS = [
  { label: "批准继续", value: "approve", description: "接受当前信息并恢复工作流。" },
  { label: "反馈后重规划", value: "feedback", description: "补充结构反馈并让后端重新规划。" },
  { label: "补充约束", value: "clarify", description: "补充澄清信息后继续。" },
  { label: "终止本轮", value: "reject", description: "结束当前工作流。" }
];

function isReviewDecision(value: string): value is ReviewDecision {
  return value === "approve" || value === "feedback" || value === "clarify" || value === "reject";
}

export function ReviewCard({ attempt, isSubmitting, submitError, onSubmit }: ReviewCardProps) {
  const canReview =
    attempt.status === "interrupted" && Boolean(attempt.review.review_id) && attempt.review.status === "pending";
  const options = useMemo(() => {
    const source = attempt.review.options?.length ? attempt.review.options : FALLBACK_OPTIONS;
    return source.filter((option) => isReviewDecision(option.value));
  }, [attempt.review.options]);
  const [decision, setDecision] = useState<ReviewDecision>((options[0]?.value as ReviewDecision) ?? "approve");
  const [answersText, setAnswersText] = useState("");
  const [feedback, setFeedback] = useState("");
  const [updatedConstraintsText, setUpdatedConstraintsText] = useState("{}");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [message, setMessage] = useState("");

  if (!canReview) {
    return (
      <section className="panel review-card quiet">
        <p className="eyebrow">Review</p>
        <h2>暂无待处理评审</h2>
        <p>只有 attempt 处于 interrupted 且 review.status=pending 时才允许提交 resume。</p>
      </section>
    );
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    const result = validateReviewDraft({
      attemptId: attempt.attempt_id,
      reviewId: attempt.review.review_id,
      decision,
      answersText,
      feedback,
      updatedConstraintsText
    });
    if (!result.valid || !result.payload) {
      setMessage(result.message ?? "review 表单校验失败。");
      return;
    }
    await onSubmit(result.payload);
  }

  return (
    <section className="panel review-card">
      <div className="panel-heading">
        <p className="eyebrow accent">Human Review</p>
        <h2>{attempt.review.stage === "clarification_review" ? "前置澄清" : "架构评审"}</h2>
        <p>{attempt.review.review_id}</p>
      </div>

      <form onSubmit={handleSubmit}>
        <article className="review-question">
          <strong>{attempt.review.question || "请确认当前评审项。"}</strong>
          <details>
            <summary>上下文摘要</summary>
            <pre>{attempt.review.context_summary || "暂无上下文摘要。"}</pre>
          </details>
        </article>

        <div className="review-options" role="radiogroup" aria-label="review 决策">
          {options.map((option) => (
            <label className={decision === option.value ? "selected" : ""} key={option.value}>
              <input
                type="radio"
                name="decision"
                value={option.value}
                checked={decision === option.value}
                onChange={() => setDecision(option.value as ReviewDecision)}
              />
              <span>
                <strong>{option.label}</strong>
                <small>{option.description || option.value}</small>
              </span>
            </label>
          ))}
        </div>

        <label className="field">
          <span>{decision === "feedback" || decision === "clarify" ? "反馈说明（必填）" : "反馈说明（可选）"}</span>
          <textarea
            value={feedback}
            onChange={(event) => setFeedback(event.target.value)}
            rows={4}
            placeholder="例如：请增加总览页，并将送风机联动逻辑独立成子系统。"
          />
        </label>

        <label className="field">
          <span>answers（每行一条，可选）</span>
          <textarea
            value={answersText}
            onChange={(event) => setAnswersText(event.target.value)}
            rows={3}
            placeholder="按行填写澄清答案"
          />
        </label>

        <button className="text-button" type="button" onClick={() => setShowAdvanced((value) => !value)}>
          {showAdvanced ? "收起高级约束" : "展开 updated_constraints JSON"}
        </button>

        {showAdvanced ? (
          <label className="field">
            <span>updated_constraints</span>
            <textarea
              className="code-input"
              value={updatedConstraintsText}
              onChange={(event) => setUpdatedConstraintsText(event.target.value)}
              rows={6}
            />
          </label>
        ) : null}

        {message ? <p className="form-message danger">{message}</p> : null}
        {submitError ? <p className="form-message danger">{String((submitError as Error).message ?? submitError)}</p> : null}

        <button className="primary-button" type="submit" disabled={isSubmitting}>
          {isSubmitting ? "正在恢复..." : "提交 review 并恢复执行"}
        </button>
      </form>
    </section>
  );
}
