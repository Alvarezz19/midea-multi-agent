import { useCallback, useState } from "react";

import { workflowClient } from "../../../api/workflowClient";
import type { CreateRunRequest, CreateRunResponse } from "../../../types/workflow";

export function useCreateWorkflowRun() {
  const [data, setData] = useState<CreateRunResponse | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const createRun = useCallback(async (payload: CreateRunRequest) => {
    setIsSubmitting(true);
    setError(null);
    try {
      const response = await workflowClient.createRun(payload);
      setData(response);
      return response;
    } catch (nextError) {
      setError(nextError);
      throw nextError;
    } finally {
      setIsSubmitting(false);
    }
  }, []);

  return { data, error, isSubmitting, createRun };
}
