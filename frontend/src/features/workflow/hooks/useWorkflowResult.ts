import { useCallback, useEffect, useState } from "react";

import { workflowClient } from "../../../api/workflowClient";
import type { AttemptResult } from "../../../types/workflow";

export function useWorkflowResult(threadId: string, attemptId: string) {
  const [data, setData] = useState<AttemptResult | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refresh = useCallback(
    async (signal?: AbortSignal) => {
      setIsLoading(true);
      setError(null);
      try {
        const response = await workflowClient.getAttemptResult(threadId, attemptId, { signal });
        if (!signal?.aborted) {
          setData(response);
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
    void refresh(controller.signal);
    return () => controller.abort();
  }, [refresh]);

  return { data, error, isLoading, refresh: () => refresh() };
}
