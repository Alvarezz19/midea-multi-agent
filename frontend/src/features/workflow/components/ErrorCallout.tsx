import { getWorkflowErrorMessage, isWorkflowApiError } from "../../../api/workflowErrors";

interface ErrorCalloutProps {
  error: unknown;
  title?: string;
  onRetry?: () => void;
}

export function ErrorCallout({ error, title = "请求失败", onRetry }: ErrorCalloutProps) {
  if (!error) {
    return null;
  }

  return (
    <section className="error-callout" role="alert">
      <div>
        <p className="eyebrow danger">{title}</p>
        <strong>{getWorkflowErrorMessage(error)}</strong>
        {isWorkflowApiError(error) ? (
          <p className="muted">
            code={error.code}
            {error.status ? ` · HTTP ${error.status}` : ""}
          </p>
        ) : null}
      </div>
      {onRetry ? (
        <button className="ghost-button danger" type="button" onClick={onRetry}>
          重试
        </button>
      ) : null}
    </section>
  );
}
