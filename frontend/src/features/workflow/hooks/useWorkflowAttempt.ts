import { useCallback, useEffect, useRef, useState } from "react";

import { workflowClient } from "../../../api/workflowClient";
import type { AttemptDetail } from "../../../types/workflow";
import { getPollingDelay, shouldPollAttempt } from "../lib/pollingPolicy";

function buildSignature(attempt: AttemptDetail | null) {
  if (!attempt) {
    return "";
  }
  return [
    attempt.status,
    attempt.current_step,
    attempt.review?.review_id,
    attempt.review?.status,
    attempt.diagnostics?.verification_status,
    attempt.diagnostics?.final_route_decision
  ].join("|");
}

export function useWorkflowAttempt(threadId: string, attemptId: string) {
  const [data, setData] = useState<AttemptDetail | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const unchangedCountRef = useRef(0);
  const signatureRef = useRef("");

  const refresh = useCallback(
    async (signal?: AbortSignal) => {
      if (!threadId || !attemptId) {
        return null;
      }
      setIsRefreshing(true);
      setError(null);
      try {
        const response = await workflowClient.getAttempt(threadId, attemptId, { signal });
        if (signal?.aborted) {
          return null;
        }
        const signature = buildSignature(response);
        unchangedCountRef.current = signature === signatureRef.current ? unchangedCountRef.current + 1 : 0;
        signatureRef.current = signature;
        setData(response);
        return response;
      } catch (nextError) {
        if (!signal?.aborted && !(nextError instanceof DOMException && nextError.name === "AbortError")) {
          setError(nextError);
        }
        return null;
      } finally {
        if (!signal?.aborted) {
          setIsLoading(false);
          setIsRefreshing(false);
        }
      }
    },
    [attemptId, threadId]
  );

  useEffect(() => {
    const controller = new AbortController();
    setIsLoading(true);
    void refresh(controller.signal);
    return () => controller.abort();
  }, [refresh]);

  useEffect(() => {
    if (!shouldPollAttempt(data?.status)) {
      return undefined;
    }
    const delay = getPollingDelay(data?.status, unchangedCountRef.current);
    if (!delay) {
      return undefined;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void refresh(controller.signal);
    }, delay);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [data?.status, data?.current_step, data?.review?.review_id, refresh]);

  useEffect(() => {
    const handleFocus = () => {
      void refresh();
    };
    window.addEventListener("focus", handleFocus);
    return () => window.removeEventListener("focus", handleFocus);
  }, [refresh]);

  return { data, error, isLoading, isRefreshing, refresh: () => refresh() };
}
