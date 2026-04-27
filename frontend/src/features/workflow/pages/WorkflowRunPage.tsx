import { Link, useParams } from "react-router-dom";

import { AttemptHistoryRail } from "../components/AttemptHistoryRail";
import { AttemptStatusHeader } from "../components/AttemptStatusHeader";
import { DiagnosticsPanel } from "../components/DiagnosticsPanel";
import { ErrorCallout } from "../components/ErrorCallout";
import { ReviewCard } from "../components/ReviewCard";
import { WorkflowStageRail } from "../components/WorkflowStageRail";
import { useResumeReview } from "../hooks/useResumeReview";
import { useWorkflowAttempt } from "../hooks/useWorkflowAttempt";
import type { ResumeReviewRequest } from "../../../types/workflow";

export function WorkflowRunPage() {
  const { threadId = "", attemptId = "" } = useParams();
  const attempt = useWorkflowAttempt(threadId, attemptId);
  const resume = useResumeReview(threadId);

  async function handleResume(payload: ResumeReviewRequest) {
    await resume.resumeReview(payload);
    await attempt.refresh();
  }

  if (!threadId || !attemptId) {
    return <main className="page-shell">缺少 threadId 或 attemptId。</main>;
  }

  if (attempt.isLoading && !attempt.data) {
    return <main className="page-shell loading-page">正在加载工作流详情...</main>;
  }

  if (!attempt.data) {
    return (
      <main className="page-shell">
        <ErrorCallout error={attempt.error ?? new Error("未获取到 attempt detail。")} onRetry={attempt.refresh} />
        <Link className="ghost-button" to="/workflow">
          返回首页
        </Link>
      </main>
    );
  }

  return (
    <main className="workflow-shell">
      <AttemptStatusHeader attempt={attempt.data} isRefreshing={attempt.isRefreshing} onRefresh={attempt.refresh} />
      <ErrorCallout error={attempt.error} title="同步详情失败" onRetry={attempt.refresh} />

      <div className="workflow-grid">
        <AttemptHistoryRail threadId={threadId} currentAttemptId={attemptId} />
        <div className="workflow-main">
          <WorkflowStageRail attempt={attempt.data} />
          <DiagnosticsPanel diagnostics={attempt.data.diagnostics} progress={attempt.data.progress} />
        </div>
        <aside className="workflow-side">
          <ReviewCard
            attempt={attempt.data}
            isSubmitting={resume.isSubmitting}
            submitError={resume.error}
            onSubmit={handleResume}
          />
          <section className="panel quick-links">
            <p className="eyebrow">Views</p>
            <h2>结果与调试</h2>
            <Link className="primary-link" to={`/workflow/${threadId}/${attemptId}/result`}>
              查看结果产物
            </Link>
            <Link className="primary-link" to={`/workflow/${threadId}/${attemptId}/debug`}>
              查看 Trace / State History
            </Link>
          </section>
        </aside>
      </div>
    </main>
  );
}
