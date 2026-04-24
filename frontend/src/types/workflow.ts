export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonObject | JsonValue[];
export type JsonObject = { [key: string]: JsonValue };

export type WorkflowStatus =
  | "queued"
  | "running"
  | "interrupted"
  | "completed"
  | "rejected"
  | "failed";

export type ReviewStage = "none" | "clarification_review" | "architecture_review" | (string & {});
export type ReviewDecision = "approve" | "feedback" | "clarify" | "reject";

export interface CreateRunRequest {
  user_query: string;
  thread_id?: string;
  title?: string;
  enable_hitl_clarification?: boolean;
  enable_hitl_architecture_review?: boolean;
  enable_repair_agent?: boolean;
  runtime_metadata?: Record<string, unknown>;
}

export interface CreateRunResponse {
  thread_id: string;
  attempt_id: string;
  status: WorkflowStatus;
  poll_url: string;
  thread_url: string;
}

export interface WorkflowReviewSummary {
  review_id: string;
  stage: ReviewStage;
  status: string;
}

export interface ThreadOverview {
  thread_id: string;
  title: string;
  latest_attempt_id: string;
  latest_status: WorkflowStatus | string;
  latest_current_step: string;
  updated_at: string;
  latest_review: WorkflowReviewSummary;
}

export interface AttemptListItem {
  attempt_id: string;
  status: WorkflowStatus | string;
  current_step: string;
  started_at: string;
  finished_at: string;
  verification_status: string;
  final_route_decision: string;
}

export interface AttemptListResponse {
  thread_id: string;
  items: AttemptListItem[];
}

export interface ReviewOption {
  label: string;
  value: ReviewDecision | string;
  description?: string;
}

export interface ReviewProjection {
  review_id: string;
  stage: ReviewStage;
  status: string;
  question: string;
  options: ReviewOption[];
  context_summary: string;
}

export interface ProgressProjection {
  current_step_label: string;
  last_successful_node: string;
  node_count: number;
}

export interface DiagnosticsProjection {
  verification_status: string;
  verification_issue_summary: string;
  repair_round_count: number;
  retry_counts_by_scope: Record<string, number>;
  final_route_decision?: string;
}

export interface AttemptDetail {
  thread_id: string;
  attempt_id: string;
  status: WorkflowStatus;
  current_step: string;
  workflow_status: string;
  user_query: string;
  review: ReviewProjection;
  progress: ProgressProjection;
  diagnostics: DiagnosticsProjection;
  trace_files?: Record<string, string>;
  subtasks: unknown[];
}

export interface ResumeReviewRequest {
  attempt_id: string;
  review_id: string;
  decision: ReviewDecision;
  answers: unknown[];
  feedback: string;
  updated_constraints: Record<string, unknown>;
}

export interface ResumeReviewResponse {
  thread_id: string;
  attempt_id: string;
  status: WorkflowStatus;
  message: string;
}

export interface AttemptResultPayload {
  json_text: string;
  compile_report: Record<string, unknown>;
  verification_report: Record<string, unknown>;
}

export interface AttemptResult {
  thread_id: string;
  attempt_id: string;
  status: WorkflowStatus | string;
  result: AttemptResultPayload;
  trace_files?: Record<string, string>;
}

export interface TraceProjection {
  thread_id: string;
  attempt_id: string;
  status: WorkflowStatus | string;
  current_step: string;
  summary: Record<string, unknown>;
  review: ReviewProjection;
  diagnostics: DiagnosticsProjection;
  trace_files?: Record<string, string>;
}

export interface StateHistoryItem {
  created_at: string;
  next: string[];
  metadata: Record<string, unknown>;
  state: {
    current_step: string;
    review_status: string;
    review_id: string;
    hitl_stage: string;
    verification_status: string;
    route_decision: string;
  };
}

export interface StateHistoryProjection {
  thread_id: string;
  attempt_id: string;
  items: StateHistoryItem[];
}

export interface WorkflowHealth {
  ok: boolean;
  llm_provider: string;
  embedding_provider: string;
  checkpointer_ready: boolean;
  checkpointer_backend: string;
  checkpoint_db_path?: string;
  worker_ready: boolean;
  worker_backend: string;
  trace_root_writable: boolean;
  chroma_ready: boolean;
  collections: Record<string, boolean>;
}

export interface WorkflowErrorBody {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface WorkflowErrorEnvelope {
  error: WorkflowErrorBody;
}
