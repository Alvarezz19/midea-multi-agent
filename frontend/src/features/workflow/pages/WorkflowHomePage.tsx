import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ErrorCallout } from "../components/ErrorCallout";
import { HealthBanner } from "../components/HealthBanner";
import { RunComposer } from "../components/RunComposer";
import { useCreateWorkflowRun } from "../hooks/useCreateWorkflowRun";
import { useWorkflowHealth } from "../hooks/useWorkflowHealth";
import { loadRecentRuns, saveRecentRun } from "../lib/recentRuns";
import type { CreateRunRequest } from "../../../types/workflow";

export function WorkflowHomePage() {
  const navigate = useNavigate();
  const health = useWorkflowHealth();
  const create = useCreateWorkflowRun();
  const [recentVersion, setRecentVersion] = useState(0);
  const recentRuns = useMemo(() => loadRecentRuns(), [recentVersion]);

  async function handleSubmit(payload: CreateRunRequest, title: string, userQuery: string) {
    const response = await create.createRun(payload);
    saveRecentRun(response, title || payload.title || "未命名工作流", userQuery);
    setRecentVersion((value) => value + 1);
    navigate(`/workflow/${response.thread_id}/${response.attempt_id}`);
  }

  return (
    <main className="home-shell">
      <section className="hero-card">
        <div className="hero-orb" aria-hidden="true" />
        <RunComposer isSubmitting={create.isSubmitting} onSubmit={handleSubmit} />
      </section>

      <aside className="home-aside">
        <HealthBanner health={health.data} error={health.error} isLoading={health.isLoading} onRefresh={health.refresh} />
        <ErrorCallout error={create.error} title="创建运行失败" />
        <section className="panel recent-panel">
          <div className="panel-heading">
            <p className="eyebrow">Local Recent</p>
            <h2>最近打开</h2>
            <p>浏览器本地记录，用于刷新页面后快速恢复视图。</p>
          </div>
          <div className="recent-list">
            {recentRuns.map((item) => (
              <Link to={`/workflow/${item.thread_id}/${item.attempt_id}`} key={`${item.thread_id}-${item.attempt_id}`}>
                <strong>{item.title || "未命名工作流"}</strong>
                <span>{item.user_query}</span>
                <small>{item.thread_id}</small>
              </Link>
            ))}
            {!recentRuns.length ? <p className="muted">暂无本地运行记录。</p> : null}
          </div>
        </section>
      </aside>
    </main>
  );
}
