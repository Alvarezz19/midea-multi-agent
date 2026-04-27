# 工作流后端 API 草图

> 最后更新：2026-04-22
> 适用范围：当前仓库中的正式工作流主链、`workflow.py` / `workflow_trace.py`、Phase 8 review/HITL、trace/index 落盘机制
> 目标：给前端提供一套可立即开工的后端 API 设计，不要求本次同时落代码

## 1. 结论

当前工作流已经具备做前端接入的“内核条件”，但还没有现成的“服务层接口”。

因此，本稿建议：

1. 先落一层独立的后端 API，把 LangGraph 运行时、`thread_id`、checkpointer、trace 文件、review 恢复逻辑封装起来。
2. V1 先走“REST + 轮询”模式，保证可立即开工。
3. V1.1 再补“Server-Sent Events / WebSocket”流式进度，不把它作为首个阻塞项。

## 2. 当前代码事实

### 2.1 已有能力

- 正式入口：`workflow.run_workflow(...)`
- trace 入口：`workflow_trace.run_workflow(...)`
- 主状态中已有前端强相关字段：
  - `current_step`
  - `review_request`
  - `review_response`
  - `review_status`
  - `review_history`
  - `final_output`
  - `verification_report`
- 当前 review 节点已经能产出直接可渲染的问答卡片：
  - `question`
  - `options`
  - `context_summary`
- trace 已支持：
  - `thread_id`
  - `attempt_id`
  - `trace_dir`
  - `summary_json`
  - `summary_md`
  - `final_state_json`
  - review 相关索引与记录文件

### 2.2 当前缺口

- 没有 HTTP API 层
- 没有统一的任务状态存储层
- 现在的正式入口是同步 `invoke()`，不适合前端直接调用
- 当前仓库里的 HITL smoke 只证明机制可用，不等于已经有生产级持久化接口

### 2.3 与 LangGraph 官方约束对齐

本稿按以下官方约束设计：

- 使用 checkpointer 时，必须通过 `config["configurable"]["thread_id"]` 指定线程
- `interrupt()` 触发后，暂停信息会通过 `__interrupt__` 暴露给调用方
- 恢复执行要用 `Command(resume=...)`
- `get_state()` / `get_state_history()` 可用于前端状态查询和审计
- 生产环境应使用持久化 checkpointer，而不是仅用内存 saver

参考：

- LangGraph Persistence: https://docs.langchain.com/oss/python/langgraph/persistence
- LangGraph Interrupts: https://docs.langchain.com/oss/python/langgraph/interrupts
- LangGraph Streaming: https://docs.langchain.com/oss/python/langgraph/streaming

## 3. 设计目标

### 3.1 本稿覆盖

- 发起一次工作流运行
- 查询当前运行状态
- 命中 review 时暂停并返回审批卡片
- 提交审批/补充信息后恢复执行
- 获取最终结果与 trace 文件索引
- 查询同一 `thread_id` 的 attempt 历史

### 3.2 本稿不覆盖

- 用户系统、鉴权、租户隔离
- 前端页面样式和组件实现
- 持久化数据库表的最终技术选型
- 流式 token 输出
- `Send` 并行派发和 reducer fan-in

## 4. 资源模型

建议把后端对外资源固定为 3 类：

### 4.1 Workflow Thread

表示一条可持续恢复的会话主线，对应 LangGraph 的 `thread_id`。

建议字段：

- `thread_id`
- `title`
- `created_at`
- `updated_at`
- `latest_attempt_id`
- `latest_status`

### 4.2 Workflow Attempt

表示一次具体运行，对应当前 trace 里的 `attempt_id`。

建议字段：

- `attempt_id`
- `thread_id`
- `status`
- `user_query`
- `current_step`
- `started_at`
- `finished_at`
- `review_id`
- `review_stage`
- `verification_status`
- `final_route_decision`
- `trace_files`

### 4.3 Review Task

表示一次可恢复的人机审阅点。

建议字段：

- `review_id`
- `thread_id`
- `attempt_id`
- `stage`
- `status`
- `question`
- `options`
- `context_summary`
- `resume_schema`

## 5. 状态机口径

后端对前端暴露的运行状态建议统一为：

| 状态 | 含义 | 典型来源 |
| --- | --- | --- |
| `queued` | 已创建，等待执行 | 服务层任务队列 |
| `running` | 正在执行 | worker 正在跑图 |
| `interrupted` | 等待人工 review/resume | `__interrupt__` / `review_status=pending` |
| `completed` | 正常完成 | `route_decision=accept` 或 `verification_report.status=passed` |
| `rejected` | 被人工终止或修复拒绝 | `final_output.review_abort` / `route_decision=reject` |
| `failed` | 异常失败 | worker 异常、依赖异常、未捕获异常 |

注意：

- `current_step` 保留工作流内部节点粒度
- `status` 是给前端看的产品态，不要直接复用所有内部状态值

## 6. API 方案

统一前缀建议为：`/api/workflow`

### 6.1 创建并启动运行

`POST /api/workflow/runs`

用途：

- 新建 thread
- 创建一次 attempt
- 提交后台执行

请求体：

```json
{
  "user_query": "为 AHU 生成送风机与电加热联动控制",
  "thread_id": "",
  "title": "AHU 控制方案",
  "enable_hitl_clarification": true,
  "enable_hitl_architecture_review": true,
  "runtime_metadata": {
    "source": "frontend",
    "operator": "demo_user"
  }
}
```

规则：

- `thread_id` 为空时，由后端生成
- 若任一 HITL 开关为 `true`，后端必须启用持久化 checkpointer
- 建议默认走 `workflow_trace.run_workflow(...)`，而不是 `workflow.run_workflow(...)`

响应：

```json
{
  "thread_id": "wf_20260422_001",
  "attempt_id": "20260422_103501_123456",
  "status": "queued",
  "poll_url": "/api/workflow/threads/wf_20260422_001/attempts/20260422_103501_123456",
  "thread_url": "/api/workflow/threads/wf_20260422_001"
}
```

### 6.2 查询 thread 概览

`GET /api/workflow/threads/{thread_id}`

用途：

- 前端刷新页面时恢复会话主视图
- 展示最新状态和最近一次 attempt

响应：

```json
{
  "thread_id": "wf_20260422_001",
  "title": "AHU 控制方案",
  "latest_attempt_id": "20260422_103501_123456",
  "latest_status": "interrupted",
  "latest_current_step": "architecture_review_prepared",
  "updated_at": "2026-04-22T10:35:20+08:00",
  "latest_review": {
    "review_id": "architecture_review-0001",
    "stage": "architecture_review",
    "status": "pending"
  }
}
```

### 6.3 查询单次运行详情

`GET /api/workflow/threads/{thread_id}/attempts/{attempt_id}`

用途：

- 前端轮询核心接口
- 工作流详情页主数据接口

响应建议：

```json
{
  "thread_id": "wf_20260422_001",
  "attempt_id": "20260422_103501_123456",
  "status": "interrupted",
  "current_step": "architecture_review_prepared",
  "workflow_status": "interrupted",
  "user_query": "为 AHU 生成送风机与电加热联动控制",
  "review": {
    "review_id": "architecture_review-0001",
    "stage": "architecture_review",
    "status": "pending",
    "question": "请确认当前系统骨架是否可继续进入子系统规划；若需调整，请只反馈需求或约束层修改意见。",
    "options": [
      {"label": "批准继续", "value": "approve", "description": "接受当前骨架并继续子系统规划。"},
      {"label": "反馈后重规划", "value": "feedback", "description": "补充结构约束并重跑 architecture_planning。"},
      {"label": "补充约束", "value": "clarify", "description": "补充需求信息后重跑 architecture_planning。"},
      {"label": "终止本轮", "value": "reject", "description": "结束当前工作流。"}
    ],
    "context_summary": "页面列表：控制\n子系统列表：supply_fan_ctrl\n共享信号摘要：\n- supply_fan_available_flag: owner=supply_fan_ctrl; consumers=无"
  },
  "progress": {
    "current_step_label": "架构评审",
    "last_successful_node": "architecture_planning",
    "node_count": 6
  },
  "diagnostics": {
    "verification_status": "",
    "verification_issue_summary": "",
    "repair_round_count": 0,
    "retry_counts_by_scope": {
      "planning": 0,
      "assembly": 0,
      "compile": 0
    }
  },
  "trace_files": {
    "trace_dir": "",
    "summary_json": "",
    "summary_md": "",
    "final_state_json": ""
  }
}
```

约束：

- 该接口不要直接原样返回整个 `WorkflowState`
- 只返回前端当前页面真正需要的投影字段

### 6.4 提交 review / 恢复执行

`POST /api/workflow/threads/{thread_id}/resume`

用途：

- 消费 `review_request`
- 调用 `Command(resume=payload)` 继续执行

请求体：

```json
{
  "attempt_id": "20260422_103501_123456",
  "review_id": "architecture_review-0001",
  "decision": "feedback",
  "answers": ["请增加总览页"],
  "feedback": "结构上需要在子系统规划前补一个总览页。",
  "updated_constraints": {
    "required_pages": ["控制", "总览"],
    "assumptions": ["增加总览页后再进入子系统规划。"]
  }
}
```

规则：

- `review_id` 必传，并且必须与当前挂起 review 一致
- 若当前线程没有挂起 review，返回 `409 Conflict`
- 恢复后后端应创建新的 worker 继续跑到下一次暂停或结束

响应：

```json
{
  "thread_id": "wf_20260422_001",
  "attempt_id": "20260422_103501_123456",
  "status": "running",
  "message": "review 已提交，工作流继续执行中。"
}
```

### 6.5 查询 attempt 历史

`GET /api/workflow/threads/{thread_id}/attempts`

用途：

- 会话侧边栏
- 历史运行列表

响应：

```json
{
  "thread_id": "wf_20260422_001",
  "items": [
    {
      "attempt_id": "20260422_103501_123456",
      "status": "completed",
      "current_step": "verification_completed",
      "started_at": "2026-04-22T10:35:01+08:00",
      "finished_at": "2026-04-22T10:35:18+08:00",
      "verification_status": "passed",
      "final_route_decision": "accept"
    }
  ]
}
```

### 6.6 查询最终结果

`GET /api/workflow/threads/{thread_id}/attempts/{attempt_id}/result`

用途：

- 结果页
- 导出按钮
- 调试信息展开面板

响应：

```json
{
  "thread_id": "wf_20260422_001",
  "attempt_id": "20260422_103501_123456",
  "status": "completed",
  "result": {
    "json_text": "{...}",
    "compile_report": {
      "page_count": 2,
      "subflow_count": 1,
      "node_count": 48,
      "warnings": []
    },
    "verification_report": {
      "status": "passed",
      "repair_scope": "none",
      "issue_summary": "ok",
      "issues": [],
      "warnings": [],
      "metrics": {
        "missing_required_inputs": 0,
        "isolated_nodes": 0,
        "invalid_port_refs": 0
      }
    }
  },
  "trace_files": {
    "trace_dir": "D:/yjsproject/midea/outputs/workflow_trace_20260422_103501_123456",
    "summary_json": "D:/yjsproject/midea/outputs/workflow_trace_20260422_103501_123456/workflow_node_io_record.json",
    "summary_md": "D:/yjsproject/midea/outputs/workflow_trace_20260422_103501_123456/workflow_node_io_record.md",
    "final_state_json": "D:/yjsproject/midea/outputs/workflow_trace_20260422_103501_123456/final_state.json"
  }
}
```

### 6.7 查询 trace 摘要

`GET /api/workflow/threads/{thread_id}/attempts/{attempt_id}/trace`

用途：

- 前端调试页
- 运行过程摘要

建议只返回摘要，不直接返回所有节点 IO 明细。

### 6.8 健康检查

`GET /api/workflow/health`

建议返回：

```json
{
  "ok": true,
  "llm_provider": "deepseek",
  "embedding_provider": "bge",
  "checkpointer_ready": true,
  "chroma_ready": true,
  "collections": {
    "atomic_modules": true,
    "subflow_templates": true,
    "system_patterns": true
  }
}
```

这个接口必须做，因为当前检索库缺失时，系统可能只会返回空切片，不一定立刻硬失败。

## 7. DTO 草图

### 7.1 `CreateRunRequest`

```json
{
  "type": "object",
  "required": ["user_query"],
  "properties": {
    "user_query": {"type": "string", "minLength": 1},
    "thread_id": {"type": "string"},
    "title": {"type": "string"},
    "enable_hitl_clarification": {"type": "boolean"},
    "enable_hitl_architecture_review": {"type": "boolean"},
    "runtime_metadata": {"type": "object"}
  }
}
```

### 7.2 `ResumeReviewRequest`

```json
{
  "type": "object",
  "required": ["attempt_id", "review_id", "decision"],
  "properties": {
    "attempt_id": {"type": "string"},
    "review_id": {"type": "string"},
    "decision": {
      "type": "string",
      "enum": ["approve", "feedback", "clarify", "reject"]
    },
    "answers": {
      "type": "array",
      "items": {"type": "string"}
    },
    "feedback": {"type": "string"},
    "updated_constraints": {"type": "object"}
  }
}
```

### 7.3 `ErrorResponse`

```json
{
  "error": {
    "code": "review_conflict",
    "message": "当前线程没有待处理的 review，无法恢复执行。",
    "details": {
      "thread_id": "wf_20260422_001",
      "attempt_id": "20260422_103501_123456"
    }
  }
}
```

## 8. 推荐实现方式

## 8.1 服务层分层

建议新增：

- `app/api/workflow_api.py`
- `app/services/workflow_service.py`
- `app/services/workflow_state_projection.py`
- `app/services/checkpointer_factory.py`
- `app/repositories/workflow_run_repository.py`

职责：

- `workflow_api.py`
  - HTTP 入参校验
  - 返回码映射
- `workflow_service.py`
  - 调用 `workflow_trace.run_workflow(...)`
  - 调用 `graph.invoke(Command(resume=...), config)`
  - 读取 `get_state()` / `get_state_history()`
- `workflow_state_projection.py`
  - 把内部 `WorkflowState` 投影成前端 DTO
- `checkpointer_factory.py`
  - 提供统一 checkpointer
- `workflow_run_repository.py`
  - 存线程、attempt、状态、时间戳、错误信息

### 8.2 运行模型

V1 建议：

- HTTP 请求只负责“提交任务”
- 真正执行在后台 worker
- 前端通过轮询拿状态

不建议：

- 在 HTTP 请求线程里直接同步跑完整个工作流
- 前端直接调用 `workflow.py`
- 前端直接读取 `outputs/` 目录文件

### 8.3 结果投影

前端主页面建议只关心：

- `status`
- `current_step`
- `review`
- `verification_status`
- `verification_issue_summary`
- `json_text`
- `compile_report`
- `trace_files`

不要把这些直接暴露给前端作为主模型：

- 完整 `analysis_result`
- 完整 `retrieval_bundle`
- 完整 `assembled_graph_ir`
- 完整 `subsystem_plan_map`

这些对象体积大，而且包含大量只适合调试的内部信息。

## 9. V1 与 V1.1 边界

### 9.1 V1

- `POST /runs`
- `GET /threads/{thread_id}`
- `GET /threads/{thread_id}/attempts/{attempt_id}`
- `POST /threads/{thread_id}/resume`
- `GET /threads/{thread_id}/attempts`
- `GET /threads/{thread_id}/attempts/{attempt_id}/result`
- `GET /health`

前端能力：

- 发起任务
- 轮询状态
- review 审批
- 看最终结果
- 看历史 attempts

### 9.2 V1.1

- `GET /threads/{thread_id}/attempts/{attempt_id}/events`

建议用 SSE。

理由：

- 当前工作流还没有现成的服务层 streaming 封装
- SSE 比 WebSocket 更适合先做“单向进度事件”
- 后续若切 `graph.stream(..., stream_mode=["updates"], version="v2")`，也更容易接进去

## 10. 为 Send / reducer 预留的兼容设计约束

本节的目标不是提前实现 `Send` 并行派发和 reducer fan-in，而是保证现在开始做前后端时，不把后续正式迁移路径堵死。

### 10.1 外部 API 不暴露 LangGraph 内部并行语义

当前对外 API 不应直接暴露这些内部实现概念：

- `Send`
- reducer
- worker node
- fan-out
- fan-in
- super-step

原因：

- 这些都是 LangGraph 图内部执行细节，不是前端必须理解的产品概念
- 后续即使从串行 `subsystem_planning` 迁移到 `Send` 并行 worker，外部接口也应尽量保持不变

因此，前端只能依赖这些稳定资源概念：

- `thread_id`
- `attempt_id`
- `review_id`
- `status`
- `current_step`
- `result`
- `trace_files`

### 10.2 `status` 必须保持产品态，而不是执行拓扑态

对前端暴露的运行状态继续限定为：

- `queued`
- `running`
- `interrupted`
- `completed`
- `rejected`
- `failed`

不要新增这类直接绑定并行拓扑的状态：

- `fanout_running`
- `worker_merging`
- `reducer_pending`
- `parallel_subsystems_running`

原因：

- 这些状态只在某一版实现下成立
- 一旦后续并行策略、聚合策略或节点命名调整，前端状态机就会被迫重写

### 10.3 `current_step` 只能表示“当前主阶段”，不能承诺“唯一执行节点”

当前串行主链下，`current_step` 看起来像“唯一正在执行的节点”。

但若后续接入 `Send`：

- 同一阶段可能会同时存在多个 subsystem worker
- 同一 super-step 内可能出现多份状态更新
- reducer 聚合后才会形成下一阶段可见状态

因此现在就要约束：

- `current_step` 对外解释为“当前主阶段”
- 前端展示文案应是“当前进行到哪一阶段”
- 不应解释成“当前只有一个节点在跑”

建议映射为稳定阶段名，而不是直接拿内部 node 名做产品文案：

- `analysis`
- `clarification_review`
- `retrieval`
- `architecture_planning`
- `architecture_review`
- `subsystem_planning`
- `global_assembly`
- `coding`
- `verification`
- `repair`
- `completed`

### 10.4 进度表达不能绑定串行节点数

现在不要把进度定义成：

- “总共 10 个节点，当前跑到第 6 个，所以进度 60%”

这会在未来并行化后立即失真。

建议：

- V1 只展示阶段态，不展示精确百分比
- 如果一定要有进度条，使用粗粒度阶段进度
- 后续若接流式事件，再单独补“阶段内子任务数 / 已完成子任务数”

可接受的 V1 方案：

- `analysis` 完成
- `retrieval` 完成
- `architecture` 完成
- `subsystem_planning` 进行中
- `verification` 等待中

不建议的 V1 方案：

- 直接按节点个数平均分配百分比
- 直接按 trace `node_count` 计算进度

### 10.5 attempt 结果模型必须允许“一对多子结果”

当前 `subsystem_planning` 是串行，前端很容易误以为每次 attempt 只会产生一份中间规划结果。

为后续 `Send` 预留时，应允许 attempt 详情中后续增加这类可选结构：

```json
{
  "subtasks": [
    {
      "task_id": "subsystem:supply_fan_ctrl",
      "task_type": "subsystem_planning",
      "status": "completed"
    },
    {
      "task_id": "subsystem:coil_ctrl",
      "task_type": "subsystem_planning",
      "status": "running"
    }
  ]
}
```

约束：

- `subtasks` 现在不是必做字段
- 但后续新增它时，不应破坏现有主响应结构
- 前端现在就不要假设“一次运行永远只有单个活跃子任务”

### 10.6 DTO 必须坚持“投影层”，不要把内部聚合状态原样透出

后续 reducer 落地后，最容易变化的是这些内部对象的聚合方式：

- `subsystem_plan_map`
- 某些 review / repair 历史列表
- 某些 trace 内部统计字段
- 未来新增的 worker 级累积 key

因此必须坚持：

- API 返回的是投影 DTO，不是内部状态直出
- DTO 字段要围绕页面用途设计，而不是围绕 LangGraph state key 设计
- 内部状态可以调整 reducer 或聚合形态，而不要求前端一起改

### 10.7 事件流模型从一开始就要允许“多事件、多分支”

如果后续做 `SSE`，事件结构不要设计成“同一时刻只会有一个节点事件”。

建议预留这类结构：

```json
{
  "event_type": "state_update",
  "thread_id": "wf_20260422_001",
  "attempt_id": "20260422_103501_123456",
  "stage": "subsystem_planning",
  "updates": [
    {
      "scope": "subtask",
      "task_id": "subsystem:supply_fan_ctrl",
      "status": "completed"
    },
    {
      "scope": "subtask",
      "task_id": "subsystem:coil_ctrl",
      "status": "running"
    }
  ]
}
```

这样即使后面切到 `graph.stream(..., stream_mode=["updates"], version="v2")`，服务层也还能把多分支更新压成统一事件，不需要推翻协议。

### 10.8 review 语义必须仍然挂在 thread / attempt 上，而不是挂在某个并行 worker 上

当前 review 点在主链上：

- clarification review
- architecture review

后续即使 `subsystem_planning` 进入并行 worker，也不要把对外 review 语义拆成“每个 worker 各自 review”。

除非产品层明确需要，否则对外仍应保持：

- review 属于某个 `thread_id`
- review 属于某个 `attempt_id`
- 当前只暴露一个“主 review 卡片”

原因：

- 这能最大限度避免前端审批流被并行化细节污染
- 也更符合当前工作流里“review 是阶段门禁，不是 worker 局部确认”的定位

### 10.9 历史与 trace 模型允许未来补充 worker 级诊断，但不改主键体系

后续若接入 `Send/reducer`，可以新增：

- 子任务级 trace
- worker 级诊断
- reducer 聚合摘要

但不应改动这些主键关系：

- `thread_id` 仍是会话主键
- `attempt_id` 仍是一次运行主键
- `review_id` 仍是一次人工审阅主键

可以新增：

- `task_id`
- `parent_attempt_id`
- `task_trace_id`

不建议改成：

- 用 worker 级 ID 替代 `attempt_id`
- 前端主要页面改按 worker 维度组织

### 10.10 现在就应冻结的兼容性红线

下面这些规则建议现在就冻结：

1. `POST /runs`、`POST /resume`、`GET /attempt detail` 的请求/响应主结构，不因 `Send` 上线而推翻
2. `status` 只表示产品态
3. `current_step` 只表示主阶段
4. 前端不依赖固定串行节点数计算进度
5. API 返回 DTO 投影，不返回完整内部 state
6. `thread_id` / `attempt_id` / `review_id` 保持为外部稳定主键

一句话说，这一层兼容约束的目标是：

- 允许图内部从“串行规划”演进到“并行 fan-out + reducer 聚合”
- 但不让前端 API 因为执行拓扑变化而被迫重做

## 11. 关键业务规则

### 11.1 线程规则

- 同一个前端会话应复用同一个 `thread_id`
- 新建需求时可生成新 `thread_id`
- 恢复 review 时禁止切换 `thread_id`

### 11.2 attempt 规则

- 每次点击“开始生成”都新建一个 `attempt_id`
- 同一 `thread_id` 下可有多个 attempts
- 前端默认展示最新一次 attempt

### 11.3 review 规则

- 一个时刻只允许处理当前挂起的 `review_id`
- `review_id` 不匹配时返回 `409`
- 提交 `reject` 后，attempt 状态应转为 `rejected`

### 11.4 trace 规则

- 所有前端发起的运行都建议使用 trace 入口
- trace 文件路径由后端保存并投影给前端
- 前端不直接拼接磁盘路径

## 12. 开发顺序建议

建议按这个顺序落地：

1. 先做 `POST /runs`、`GET /attempt detail`、`POST /resume`
2. 接着做 `GET /result`、`GET /attempt list`
3. 再做 `GET /health`
4. 最后再补 SSE 事件流

原因：

- 前 3 个接口已经足够支撑“发起 -> review -> 恢复 -> 出结果”的完整链路
- SSE 不是首个业务闭环的必要条件

## 13. 落地前必须确认的前置事项

- 选定生产 checkpointer
- 明确 worker 执行模型
- 明确线程/attempt 的持久化位置
- 增加统一异常码表
- 增加环境健康检查
- 明确 trace 文件是否允许前端下载

## 14. 建议的首批任务拆分

- 任务 1：补服务骨架与路由
- 任务 2：封装 `run_workflow_trace` 的异步执行器
- 任务 3：封装 `resume review` 的恢复执行器
- 任务 4：实现状态投影 DTO
- 任务 5：实现健康检查
- 任务 6：补一组 API 合同测试

## 15. 一句话版本

前端现在可以开工，但应该对接“新增的后端服务层”，不是直接对接 LangGraph 图对象；V1 先做 `REST + 轮询 + review 恢复`，把 `thread_id`、`attempt_id`、`review_id` 固定成正式外部契约。
