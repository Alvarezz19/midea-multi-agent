import type { TraceProjection } from "../../../types/workflow";

interface TraceSummaryPanelProps {
  trace: TraceProjection | null;
}

const SUMMARY_FIELDS = [
  ["workflow_status", "工作流状态"],
  ["node_count", "节点数"],
  ["last_successful_node", "最后成功节点"],
  ["verification_status", "验收状态"],
  ["verification_issue_summary", "问题摘要"],
  ["repair_round_count", "修复轮次"],
  ["final_route_decision", "最终路由"],
  ["review_status", "Review 状态"],
  ["review_id", "Review ID"],
  ["hitl_stage", "HITL 阶段"],
  ["acceptance_summary", "验收摘要"]
] as const;

export function TraceSummaryPanel({ trace }: TraceSummaryPanelProps) {
  if (!trace) {
    return <section className="panel empty-panel">暂无 trace 摘要。</section>;
  }

  return (
    <section className="panel trace-panel">
      <div className="panel-heading">
        <p className="eyebrow">Trace Summary</p>
        <h2>瘦身运行摘要</h2>
        <p>这里只展示后端 `/trace` 投影，不读取磁盘 trace 文件。</p>
      </div>
      <dl className="summary-list">
        {SUMMARY_FIELDS.map(([key, label]) => (
          <div key={key}>
            <dt>{label}</dt>
            <dd>{String(trace.summary?.[key] ?? "暂无")}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
