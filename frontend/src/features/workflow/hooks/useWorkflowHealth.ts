import { useCallback, useEffect, useState } from "react";

import { workflowClient } from "../../../api/workflowClient";
import type { WorkflowHealth } from "../../../types/workflow";

export function useWorkflowHealth() {
  const [data, setData] = useState<WorkflowHealth | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await workflowClient.getHealth({ signal });
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
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void refresh(controller.signal);
    return () => controller.abort();
  }, [refresh]);

  return { data, error, isLoading, refresh: () => refresh() };
}
