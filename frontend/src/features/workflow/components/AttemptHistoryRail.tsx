import { Link } from "react-router-dom";

import { useThreadAttempts } from "../hooks/useThreadAttempts";

interface AttemptHistoryRailProps {
  threadId: string;
  currentAttemptId: string;
}

export function AttemptHistoryRail({ threadId, currentAttemptId }: AttemptHistoryRailProps) {
  const { thread, attempts, error, isLoading, refresh } = useThreadAttempts(threadId);

  return (
    <aside className="history-rail">
      <div className="panel-heading">
        <p className="eyebrow">Thread History</p>
        <h2>{thread?.title || "当前会话"}</h2>
        <p>{thread?.updated_at || threadId}</p>
      </div>
      <button className="ghost-button compact" type="button" onClick={refresh}>
        刷新历史
      </button>
      {isLoading ? <p className="muted">正在加载历史...</p> : null}
      {error ? <p className="form-message danger">历史加载失败：{String((error as Error).message ?? error)}</p> : null}
      <ol className="attempt-list">
        {(attempts?.items ?? []).map((item) => (
          <li className={item.attempt_id === currentAttemptId ? "active" : ""} key={item.attempt_id}>
            <Link to={`/workflow/${threadId}/${item.attempt_id}`}>
              <span className={`tiny-status ${item.status}`}>{item.status}</span>
              <strong>{item.current_step || "start"}</strong>
              <small>{item.started_at || "暂无开始时间"}</small>
              {item.verification_status || item.final_route_decision ? (
                <small>
                  {item.verification_status || "verification: -"} · {item.final_route_decision || "route: -"}
                </small>
              ) : null}
            </Link>
          </li>
        ))}
      </ol>
      {!isLoading && !attempts?.items?.length ? <p className="muted">暂无历史 attempt。</p> : null}
    </aside>
  );
}
