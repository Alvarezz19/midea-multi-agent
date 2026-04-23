import { describe, expect, it } from "vitest";

import { getStageForStep, getStageLabel } from "./currentStepMapping";

describe("currentStepMapping", () => {
  it("把内部 current_step 映射为产品阶段", () => {
    expect(getStageForStep("architecture_review_prepared")?.key).toBe("architecture_review");
    expect(getStageForStep("repair_completed")?.key).toBe("repair");
    expect(getStageLabel("verification_completed")).toBe("结构验收");
  });

  it("终态强制进入结束阶段", () => {
    expect(getStageForStep("verification_completed", "completed")?.key).toBe("done");
  });

  it("未知 step 降级展示原始值", () => {
    expect(getStageLabel("new_backend_step")).toBe("未知阶段：new_backend_step");
  });
});
