import { useCallback, useEffect, useState } from "react";

import { workflowClient } from "../../../api/workflowClient";
import type { StateHistoryProjection, TraceProjection } from "../../../types/workflow";

export function useWorkflowTrace(threadId: string, attemptId: string) {
  const [trace, setTrace] = useState<TraceProjection | null>(null);
  const [history, setHistory] = useState<StateHistoryProjection | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refresh = useCallback(
    async (limit = 10, signal?: AbortSignal) => {
      setIsLoading(true);
      setError(null);
      try {
        const [traceResponse, historyResponse] = await Promise.all([
          workflowClient.getAttemptTrace(threadId, attemptId, { signal }),
          workflowClient.getAttemptStateHistory(threadId, attemptId, limit, { signal })
        ]);
        if (!signal?.aborted) {
          setTrace(traceResponse);
          setHistory(historyResponse);
        }
      } catch (nextError) {
        if (!signal?.aborted && !(nextError instanceof DOMException && nextError.name === "AbortError")) {
          setError(nextError);
        }
      } finally {
        if (!signal?.aborted) {
          setIsLoading(false);
        }
      }
    },
    [attemptId, threadId]
  );

  useEffect(() => {
    const controller = new AbortController();
    void refresh(10, controller.signal);
    return () => controller.abort();
  }, [refresh]);

  return { trace, history, error, isLoading, refresh };
}
