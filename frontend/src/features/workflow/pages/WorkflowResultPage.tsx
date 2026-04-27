import { Link, useParams } from "react-router-dom";

import { ErrorCallout } from "../components/ErrorCallout";
import { ResultPanel } from "../components/ResultPanel";
import { useWorkflowResult } from "../hooks/useWorkflowResult";

export function WorkflowResultPage() {
  const { threadId = "", attemptId = "" } = useParams();
  const result = useWorkflowResult(threadId, attemptId);

  return (
    <main className="page-shell">
      <nav className="page-nav">
        <Link className="ghost-button" to={`/workflow/${threadId}/${attemptId}`}>
          返回运行详情
        </Link>
        <Link className="ghost-button" to={`/workflow/${threadId}/${attemptId}/debug`}>
          Trace 调试
        </Link>
      </nav>
      <ErrorCallout error={result.error} title="结果加载失败" onRetry={result.refresh} />
      <ResultPanel result={result.data} isLoading={result.isLoading} />
    </main>
  );
}
