import { Link, useParams } from "react-router-dom";

import { ErrorCallout } from "../components/ErrorCallout";
import { StateHistoryPanel } from "../components/StateHistoryPanel";
import { TraceSummaryPanel } from "../components/TraceSummaryPanel";
import { useWorkflowTrace } from "../hooks/useWorkflowTrace";

export function WorkflowDebugPage() {
  const { threadId = "", attemptId = "" } = useParams();
  const trace = useWorkflowTrace(threadId, attemptId);

  return (
    <main className="page-shell debug-shell">
      <nav className="page-nav">
        <Link className="ghost-button" to={`/workflow/${threadId}/${attemptId}`}>
          返回运行详情
        </Link>
        <Link className="ghost-button" to={`/workflow/${threadId}/${attemptId}/result`}>
          结果页
        </Link>
      </nav>
      {trace.isLoading ? <section className="panel">正在加载 trace 与 state-history...</section> : null}
      <ErrorCallout error={trace.error} title="调试数据加载失败" onRetry={() => trace.refresh()} />
      <TraceSummaryPanel trace={trace.trace} />
      <StateHistoryPanel history={trace.history} onRefresh={() => trace.refresh(10)} />
    </main>
  );
}
