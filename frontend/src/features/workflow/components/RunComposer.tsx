import { FormEvent, useState } from "react";

import type { CreateRunRequest } from "../../../types/workflow";

interface RunComposerProps {
  isSubmitting: boolean;
  onSubmit: (payload: CreateRunRequest, title: string, userQuery: string) => Promise<void>;
}

export function RunComposer({ isSubmitting, onSubmit }: RunComposerProps) {
  const [userQuery, setUserQuery] = useState("为 AHU 生成送风机与电加热联动控制");
  const [title, setTitle] = useState("AHU 控制方案");
  const [threadId, setThreadId] = useState("");
  const [enableClarification, setEnableClarification] = useState(false);
  const [enableArchitectureReview, setEnableArchitectureReview] = useState(true);
  const [message, setMessage] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    if (!userQuery.trim()) {
      setMessage("请输入自然语言需求。");
      return;
    }
    await onSubmit(
      {
        user_query: userQuery.trim(),
        thread_id: threadId.trim(),
        title: title.trim(),
        enable_hitl_clarification: enableClarification,
        enable_hitl_architecture_review: enableArchitectureReview,
        runtime_metadata: {
          source: "frontend",
          operator: "local_demo"
        }
      },
      title.trim(),
      userQuery.trim()
    );
  }

  return (
    <form className="run-composer" onSubmit={handleSubmit}>
      <div className="composer-heading">
        <p className="eyebrow">Workflow Launch</p>
        <h1>智慧楼宇控制程序生成驾驶舱</h1>
        <p>输入 AHU / 楼宇控制需求，前端将通过 REST 轮询跟踪运行、处理人工评审并展示最终 JSON 产物。</p>
      </div>

      <label className="field">
        <span>需求描述</span>
        <textarea
          value={userQuery}
          onChange={(event) => setUserQuery(event.target.value)}
          rows={8}
          placeholder="例如：为 AHU 生成送风机与电加热联动控制"
        />
      </label>

      <div className="field-grid">
        <label className="field">
          <span>标题</span>
          <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="AHU 控制方案" />
        </label>
        <label className="field">
          <span>复用 thread_id（可选）</span>
          <input
            value={threadId}
            onChange={(event) => setThreadId(event.target.value)}
            placeholder="留空则后端自动创建"
          />
        </label>
      </div>

      <div className="switch-grid" aria-label="HITL 开关">
        <label className="switch-card">
          <input
            type="checkbox"
            checked={enableArchitectureReview}
            onChange={(event) => setEnableArchitectureReview(event.target.checked)}
          />
          <span>
            <strong>架构评审</strong>
            <small>默认开启，在子系统规划前人工确认骨架。</small>
          </span>
        </label>
        <label className="switch-card">
          <input
            type="checkbox"
            checked={enableClarification}
            onChange={(event) => setEnableClarification(event.target.checked)}
          />
          <span>
            <strong>前置澄清</strong>
            <small>当需求歧义较高时暂停并要求补充信息。</small>
          </span>
        </label>
      </div>

      {message ? <p className="form-message">{message}</p> : null}

      <button className="primary-button" type="submit" disabled={isSubmitting}>
        {isSubmitting ? "正在创建..." : "创建并运行工作流"}
      </button>
    </form>
  );
}
