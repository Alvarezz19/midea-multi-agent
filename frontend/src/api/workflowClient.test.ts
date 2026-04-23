import { afterEach, describe, expect, it, vi } from "vitest";

import { WorkflowApiError } from "./workflowErrors";
import { workflowClient } from "./workflowClient";

describe("workflowClient", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("解析成功响应", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ ok: true, worker_ready: true }), { status: 200 }))
    );

    const response = await workflowClient.getHealth();
    expect(response.ok).toBe(true);
    expect(vi.mocked(fetch).mock.calls[0]?.[0]).toBe("http://127.0.0.1:8000/api/workflow/health");
  });

  it("保留后端错误 envelope", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              error: {
                code: "conflict",
                message: "review_id 不匹配",
                details: { active_review_id: "review-1" }
              }
            }),
            { status: 409 }
          )
      )
    );

    await expect(workflowClient.getAttempt("thread-1", "attempt-1")).rejects.toMatchObject({
      code: "conflict",
      status: 409,
      details: { active_review_id: "review-1" }
    });
  });

  it("网络失败归一化为 network_error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("fetch failed");
      })
    );

    await expect(workflowClient.getHealth()).rejects.toMatchObject({ code: "network_error" });
  });
});
