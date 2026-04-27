import { useCallback, useState } from "react";

import { workflowClient } from "../../../api/workflowClient";
import type { ResumeReviewRequest, ResumeReviewResponse } from "../../../types/workflow";

export function useResumeReview(threadId: string) {
  const [data, setData] = useState<ResumeReviewResponse | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const resumeReview = useCallback(
    async (payload: ResumeReviewRequest) => {
      setIsSubmitting(true);
      setError(null);
      try {
        const response = await workflowClient.resumeReview(threadId, payload);
        setData(response);
        return response;
      } catch (nextError) {
        setError(nextError);
        throw nextError;
      } finally {
        setIsSubmitting(false);
      }
    },
    [threadId]
  );

  return { data, error, isSubmitting, resumeReview };
}
