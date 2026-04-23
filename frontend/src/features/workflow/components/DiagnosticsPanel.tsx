import type { DiagnosticsProjection, ProgressProjection } from "../../../types/workflow";

interface DiagnosticsPanelProps {
  diagnostics: DiagnosticsProjection;
  progress: ProgressProjection;
}

export function DiagnosticsPanel({ diagnostics, progress }: DiagnosticsPanelProps) {
  const retryEntries = Object.entries(diagnostics.retry_counts_by_scope ?? {});

  return (
    <section className="panel diagnostics-panel">
      <div className="panel-heading">
        <p className="eyebrow">Diagnostics</p>
        <h2>运行诊断</h2>
      </div>
      <div className="metric-grid">
        <article>
          <span>最后成功节点</span>
          <strong>{progress.last_successful_node || "暂无"}</strong>
        </article>
        <article>
          <span>Trace 节点数</span>
          <strong>{progress.node_count || 0}</strong>
        </article>
        <article>
          <span>验收状态</span>
          <strong>{diagnostics.verification_status || "未完成"}</strong>
        </article>
        <article>
          <span>修复轮次</span>
          <strong>{diagnostics.repair_round_count ?? 0}</strong>
        </article>
      </div>
      <div className="diagnostic-body">
        <p>
          <span>问题摘要</span>
          {diagnostics.verification_issue_summary || "暂无结构验收问题。"}
        </p>
        <p>
          <span>最终路由</span>
          {diagnostics.final_route_decision || "暂无"}
        </p>
        <div>
          <span>Retry scope</span>
          {retryEntries.length ? (
            <ul className="chip-list">
              {retryEntries.map(([scope, count]) => (
                <li key={scope}>
                  {scope}: {count}
                </li>
              ))}
            </ul>
          ) : (
            <p>暂无 retry 记录。</p>
          )}
        </div>
      </div>
    </section>
  );
}
