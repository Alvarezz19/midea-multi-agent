import type { StateHistoryProjection } from "../../../types/workflow";

interface StateHistoryPanelProps {
  history: StateHistoryProjection | null;
  onRefresh: () => void;
}

export function StateHistoryPanel({ history, onRefresh }: StateHistoryPanelProps) {
  return (
    <section className="panel state-history-panel">
      <div className="panel-heading split">
        <div>
          <p className="eyebrow">State History</p>
          <h2>调试态历史</h2>
          <p>只展示瘦身 state，不暴露完整 values。</p>
        </div>
        <button className="ghost-button" type="button" onClick={onRefresh}>
          手动刷新
        </button>
      </div>
      {!history?.items?.length ? <p className="muted">暂无 state-history 记录。</p> : null}
      <ol className="history-list">
        {(history?.items ?? []).map((item, index) => (
          <li key={`${item.created_at}-${index}`}>
            <div>
              <strong>{item.created_at || `snapshot-${index + 1}`}</strong>
              <small>next: {item.next.length ? item.next.join(", ") : "[]"}</small>
              <small>metadata.step: {String(item.metadata.step ?? "暂无")}</small>
            </div>
            <pre>{JSON.stringify(item.state, null, 2)}</pre>
          </li>
        ))}
      </ol>
    </section>
  );
}
