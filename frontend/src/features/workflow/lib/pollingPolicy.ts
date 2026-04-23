import type { WorkflowStatus } from "../../../types/workflow";

export function shouldPollAttempt(status?: WorkflowStatus | string) {
  return status === "queued" || status === "running";
}

export function getPollingDelay(status?: WorkflowStatus | string, unchangedCount = 0) {
  if (!shouldPollAttempt(status)) {
    return null;
  }
  return unchangedCount >= 5 ? 3000 : 1500;
}

export function isTerminalStatus(status?: WorkflowStatus | string) {
  return status === "completed" || status === "rejected" || status === "failed";
}
