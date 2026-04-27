import { Link } from "react-router-dom";

import type { AttemptDetail } from "../../../types/workflow";
import { getStageLabel } from "../lib/currentStepMapping";

const STATUS_LABELS: Record<string, string> = {
  queued: "排队中",
  running: "运行中",
  interrupted: "等待人工评审",
  completed: "已完成",
  rejected: "已终止",
  failed: "失败"
};

interface AttemptStatusHeaderProps {
  attempt: AttemptDetail;
  isRefreshing: boolean;
  onRefresh: () => void;
}

export function AttemptStatusHeader({ attempt, isRefreshing, onRefresh }: AttemptStatusHeaderProps) {
  const stageLabel = getStageLabel(attempt.current_step, attempt.status);

  return (
    <header className="attempt-header">
      <div className="attempt-title-block">
        <p className="eyebrow">Thread / Attempt</p>
        <h1>{stageLabel}</h1>
        <p>{attempt.user_query}</p>
      </div>
      <div className="attempt-meta-card">
        <span className={`status-badge ${attempt.status}`}>{STATUS_LABELS[attempt.status] ?? attempt.status}</span>
        <dl>
          <div>
            <dt>thread</dt>
            <dd>{attempt.thread_id}</dd>
          </div>
          <div>
            <dt>attempt</dt>
            <dd>{attempt.attempt_id}</dd>
          </div>
          <div>
            <dt>current_step</dt>
            <dd>{attempt.current_step || "start"}</dd>
          </div>
        </dl>
        <nav className="header-actions" aria-label="工作流视图">
          <Link className="ghost-button" to="/workflow">
            返回启动页
          </Link>
          <button className="ghost-button" type="button" onClick={onRefresh} disabled={isRefreshing}>
            {isRefreshing ? "同步中" : "刷新"}
          </button>
          <Link className="ghost-button" to={`/workflow/${attempt.thread_id}/${attempt.attempt_id}/result`}>
            结果
          </Link>
          <Link className="ghost-button" to={`/workflow/${attempt.thread_id}/${attempt.attempt_id}/debug`}>
            Trace
          </Link>
        </nav>
      </div>
    </header>
  );
}
