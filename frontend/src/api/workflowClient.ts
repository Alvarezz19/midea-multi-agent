import { WorkflowApiError, makeNetworkError } from "./workflowErrors";
import type {
  AttemptDetail,
  AttemptListResponse,
  AttemptResult,
  CreateRunRequest,
  CreateRunResponse,
  ResumeReviewRequest,
  ResumeReviewResponse,
  StateHistoryProjection,
  ThreadOverview,
  TraceProjection,
  WorkflowErrorEnvelope,
  WorkflowHealth
} from "../types/workflow";

interface RequestOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
}

const DEFAULT_TIMEOUT_MS = 30_000;
const API_BASE_URL = (import.meta.env.VITE_WORKFLOW_API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

function buildUrl(path: string) {
  return `${API_BASE_URL}${path}`;
}

async function parseJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function isErrorEnvelope(payload: unknown): payload is WorkflowErrorEnvelope {
  return (
    typeof payload === "object" &&
    payload !== null &&
    "error" in payload &&
    typeof (payload as WorkflowErrorEnvelope).error?.code === "string"
  );
}

async function requestJson<T>(path: string, init: RequestInit = {}, options: RequestOptions = {}): Promise<T> {
  const controller = new AbortController();
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const timeoutId = window.setTimeout(() => {
    controller.abort("timeout");
  }, timeoutMs);

  const abortFromCaller = () => controller.abort(options.signal?.reason ?? "cancelled");
  if (options.signal) {
    if (options.signal.aborted) {
      abortFromCaller();
    } else {
      options.signal.addEventListener("abort", abortFromCaller, { once: true });
    }
  }

  try {
    const headers = new Headers(init.headers);
    headers.set("Accept", "application/json");
    if (init.body && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    const response = await fetch(buildUrl(path), {
      ...init,
      headers,
      signal: controller.signal
    });
    const payload = await parseJson(response);
    if (!response.ok) {
      if (isErrorEnvelope(payload)) {
        throw new WorkflowApiError(payload.error, response.status);
      }
      throw new WorkflowApiError(
        {
          code: "http_error",
          message: `请求失败，HTTP ${response.status}。`,
          details: { status: response.status }
        },
        response.status
      );
    }
    return payload as T;
  } catch (error) {
    if (error instanceof WorkflowApiError) {
      throw error;
    }
    if (controller.signal.aborted && options.signal?.aborted) {
      throw new DOMException("请求已取消。", "AbortError");
    }
    if (controller.signal.aborted) {
      throw new WorkflowApiError({ code: "timeout", message: "请求超时。", details: { timeoutMs } }, 0);
    }
    throw makeNetworkError(error instanceof Error ? error.message : undefined);
  } finally {
    window.clearTimeout(timeoutId);
    options.signal?.removeEventListener("abort", abortFromCaller);
  }
}

export const workflowClient = {
  createRun(payload: CreateRunRequest, options?: RequestOptions) {
    return requestJson<CreateRunResponse>(
      "/api/workflow/runs",
      {
        method: "POST",
        body: JSON.stringify(payload)
      },
      options
    );
  },

  getThread(threadId: string, options?: RequestOptions) {
    return requestJson<ThreadOverview>(`/api/workflow/threads/${encodeURIComponent(threadId)}`, {}, options);
  },

  listAttempts(threadId: string, options?: RequestOptions) {
    return requestJson<AttemptListResponse>(
      `/api/workflow/threads/${encodeURIComponent(threadId)}/attempts`,
      {},
      options
    );
  },

  getAttempt(threadId: string, attemptId: string, options?: RequestOptions) {
    return requestJson<AttemptDetail>(
      `/api/workflow/threads/${encodeURIComponent(threadId)}/attempts/${encodeURIComponent(attemptId)}`,
      {},
      options
    );
  },

  resumeReview(threadId: string, payload: ResumeReviewRequest, options?: RequestOptions) {
    return requestJson<ResumeReviewResponse>(
      `/api/workflow/threads/${encodeURIComponent(threadId)}/resume`,
      {
        method: "POST",
        body: JSON.stringify(payload)
      },
      options
    );
  },

  getAttemptResult(threadId: string, attemptId: string, options?: RequestOptions) {
    return requestJson<AttemptResult>(
      `/api/workflow/threads/${encodeURIComponent(threadId)}/attempts/${encodeURIComponent(attemptId)}/result`,
      {},
      options
    );
  },

  getAttemptTrace(threadId: string, attemptId: string, options?: RequestOptions) {
    return requestJson<TraceProjection>(
      `/api/workflow/threads/${encodeURIComponent(threadId)}/attempts/${encodeURIComponent(attemptId)}/trace`,
      {},
      options
    );
  },

  getAttemptStateHistory(threadId: string, attemptId: string, limit = 10, options?: RequestOptions) {
    return requestJson<StateHistoryProjection>(
      `/api/workflow/threads/${encodeURIComponent(threadId)}/attempts/${encodeURIComponent(
        attemptId
      )}/state-history?limit=${encodeURIComponent(String(limit))}`,
      {},
      options
    );
  },

  getHealth(options?: RequestOptions) {
    return requestJson<WorkflowHealth>("/api/workflow/health", {}, { timeoutMs: 10_000, ...options });
  }
};
