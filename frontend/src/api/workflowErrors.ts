import type { WorkflowErrorBody } from "../types/workflow";

export class WorkflowApiError extends Error {
  readonly code: string;
  readonly details: Record<string, unknown>;
  readonly status: number;

  constructor(body: WorkflowErrorBody, status = 0) {
    super(body.message);
    this.name = "WorkflowApiError";
    this.code = body.code;
    this.details = body.details ?? {};
    this.status = status;
  }
}

export function isWorkflowApiError(error: unknown): error is WorkflowApiError {
  return error instanceof WorkflowApiError;
}

export function getWorkflowErrorMessage(error: unknown): string {
  if (isWorkflowApiError(error)) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "未知错误。";
}

export function makeNetworkError(message = "网络请求失败，请检查后端服务或跨域配置。") {
  return new WorkflowApiError({ code: "network_error", message, details: {} }, 0);
}
