import { useCallback, useEffect, useState } from "react";

import { workflowClient } from "../../../api/workflowClient";
import type { AttemptListResponse, ThreadOverview } from "../../../types/workflow";

export function useThreadAttempts(threadId: string) {
  const [thread, setThread] = useState<ThreadOverview | null>(null);
  const [attempts, setAttempts] = useState<AttemptListResponse | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refresh = useCallback(
    async (signal?: AbortSignal) => {
      setIsLoading(true);
      setError(null);
      try {
        const [threadResponse, attemptsResponse] = await Promise.all([
          workflowClient.getThread(threadId, { signal }),
          workflowClient.listAttempts(threadId, { signal })
        ]);
        if (!signal?.aborted) {
          setThread(threadResponse);
          setAttempts(attemptsResponse);
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
    [threadId]
  );

  useEffect(() => {
    const controller = new AbortController();
    void refresh(controller.signal);
    return () => controller.abort();
  }, [refresh]);

  return { thread, attempts, error, isLoading, refresh: () => refresh() };
}
