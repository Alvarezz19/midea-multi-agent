import type { WorkflowHealth } from "../../../types/workflow";
import { ErrorCallout } from "./ErrorCallout";

interface HealthBannerProps {
  health: WorkflowHealth | null;
  error: unknown;
  isLoading: boolean;
  onRefresh: () => void;
}

export function HealthBanner({ health, error, isLoading, onRefresh }: HealthBannerProps) {
  if (error) {
    return <ErrorCallout error={error} title="健康检查失败" onRetry={onRefresh} />;
  }

  if (isLoading) {
    return (
      <section className="health-banner pending">
        <span className="pulse-dot" />
        正在检查 Workflow API 运行依赖...
      </section>
    );
  }

  if (!health) {
    return null;
  }

  const unhealthyCollections = Object.entries(health.collections ?? {})
    .filter(([, ready]) => !ready)
    .map(([name]) => name);

  return (
    <section className={`health-banner ${health.ok && health.chroma_ready ? "ok" : "warning"}`}>
      <div>
        <p className="eyebrow">API Health</p>
        <h2>{health.ok ? "后端执行层可用" : "后端存在联调风险"}</h2>
        <p>
          checkpointer={health.checkpointer_backend || "unknown"} · worker={health.worker_backend || "unknown"} ·
          LLM={health.llm_provider || "unknown"} · embedding={health.embedding_provider || "unknown"}
        </p>
        {!health.chroma_ready && unhealthyCollections.length ? (
          <p className="warning-text">Chroma collection 未就绪：{unhealthyCollections.join("、")}</p>
        ) : null}
      </div>
      <button className="ghost-button" type="button" onClick={onRefresh}>
        刷新健康状态
      </button>
    </section>
  );
}
