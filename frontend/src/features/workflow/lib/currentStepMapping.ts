import type { WorkflowStatus } from "../../../types/workflow";

export interface WorkflowStage {
  key: string;
  label: string;
  description: string;
  match: (step: string) => boolean;
}

export const WORKFLOW_STAGES: WorkflowStage[] = [
  {
    key: "input",
    label: "等待开始",
    description: "接收自然语言需求",
    match: (step) => step === "start" || !step
  },
  {
    key: "analysis",
    label: "需求理解",
    description: "结构化需求与歧义信号",
    match: (step) => step === "analysis_completed" || step === "ambiguity_routed"
  },
  {
    key: "clarification",
    label: "前置澄清",
    description: "必要时冻结澄清问题",
    match: (step) => step === "clarification_skipped" || step.startsWith("clarification_review_") || step === "clarification_applied"
  },
  {
    key: "retrieval",
    label: "资产检索",
    description: "匹配原子模块和 AHU 模板",
    match: (step) => step === "retrieval_completed"
  },
  {
    key: "architecture",
    label: "架构规划",
    description: "生成页面、子系统与共享信号骨架",
    match: (step) => step === "architecture_planned"
  },
  {
    key: "architecture_review",
    label: "架构评审",
    description: "人工确认或反馈系统骨架",
    match: (step) =>
      step === "architecture_review_skipped" ||
      step.startsWith("architecture_review_") ||
      step.startsWith("architecture_feedback_")
  },
  {
    key: "subsystem",
    label: "子系统规划",
    description: "生成局部 IR 与接口绑定",
    match: (step) => step === "subsystem_planned"
  },
  {
    key: "assembly",
    label: "全局装配",
    description: "合并多页签 Graph IR",
    match: (step) => step === "global_assembly_completed"
  },
  {
    key: "coding",
    label: "确定性编译",
    description: "编译为前端可展示的 JSON 产物",
    match: (step) => step === "coding_completed"
  },
  {
    key: "verification",
    label: "结构验收",
    description: "检查规划、装配与编译质量",
    match: (step) => step === "verification_completed"
  },
  {
    key: "repair",
    label: "自动修复",
    description: "按 scope 预算进行局部修复",
    match: (step) => step.startsWith("repair_")
  },
  {
    key: "done",
    label: "结束",
    description: "生成完成、终止或失败",
    match: () => false
  }
];

export function getStageForStep(currentStep: string, status?: WorkflowStatus | string) {
  if (status === "completed" || status === "rejected" || status === "failed") {
    return WORKFLOW_STAGES[WORKFLOW_STAGES.length - 1];
  }
  const normalized = (currentStep || "start").trim();
  return WORKFLOW_STAGES.find((stage) => stage.match(normalized)) ?? null;
}

export function getStageLabel(currentStep: string, status?: WorkflowStatus | string) {
  const stage = getStageForStep(currentStep, status);
  if (stage) {
    return stage.label;
  }
  return `未知阶段：${currentStep || "空"}`;
}

export function getStageIndex(currentStep: string, status?: WorkflowStatus | string) {
  const stage = getStageForStep(currentStep, status);
  if (!stage) {
    return -1;
  }
  return WORKFLOW_STAGES.findIndex((item) => item.key === stage.key);
}
