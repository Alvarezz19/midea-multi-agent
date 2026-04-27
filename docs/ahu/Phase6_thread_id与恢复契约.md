# Phase 6 thread_id 与恢复契约

> 更新时间：2026-04-17  
> 目标：为后续把 `checkpointer + thread_id + interrupt / resume` 接入正式主链提供统一协议。  
> 当前边界：正式 `workflow.py` / `workflow_trace.py` 仍未接 `checkpointer`，本文件只定义准入前必须先明确的契约。  
> 参考：  
> - <https://docs.langchain.com/oss/python/langgraph/persistence>  
> - <https://docs.langchain.com/oss/python/langgraph/interrupts>  
> - <https://docs.langchain.com/oss/python/langgraph/durable-execution>

---

## 1. 当前正式结论

- 当前仓库只有 `scripts/poc_phase4_hitl.py` 真实使用了 `checkpointer + configurable.thread_id + interrupt + Command(resume=...)`。
- 正式入口 `workflow.run_workflow(...)` 与 `workflow_trace.run_workflow(...)` 还没有 `thread_id` 参数，也没有 `checkpointer`。
- 因此，本文件不是“现状说明”，而是“Phase 7 开工前必须先遵守的契约”。

---

## 2. `thread_id` 的职责

`thread_id` 是 durable execution 的会话主键，用于把下列对象稳定关联到同一条恢复链上：

- LangGraph checkpoint 历史
- 人工审批记录
- 同一会话下的多次 `resume`
- trace / output 的 attempt 索引
- 后续审计与排障记录

`thread_id` 不是：

- `trace_dir`
- `run_dir`
- 时间戳目录名
- 节点内部临时 ID

---

## 3. 生成与归属

### 3.1 生成方

- `thread_id` 必须由最外层调用方生成。
- 禁止在图节点内部生成。
- 禁止把 `trace_dir`、`workflow_trace_<timestamp>` 之类时间戳目录直接当作 `thread_id`。

### 3.2 推荐格式

推荐使用“可审计但不携带业务敏感信息”的稳定字符串，例如：

```text
midea-<scene>-<session_or_ticket_id>
```

约束：

- 全局唯一
- 可跨首次执行与后续恢复复用
- 不依赖当前时间重新生成

### 3.3 归属对象

- 一个“用户可感知的工作流会话 / 审批单 / 修复单”对应一个稳定的 `thread_id`
- 同一个 `thread_id` 下可以有多个 attempt
- 同一个 `thread_id` 下的 `get_state / get_state_history / Command(resume=...)` 必须复用相同值

---

## 4. 传入入口

未来正式入口建议扩成显式可选参数：

```python
run_workflow(user_query: str, *, thread_id: str | None = None, ...)
```

进入主链后的最低要求：

- 若图启用 `checkpointer`，则 `invoke/configurable.thread_id` 必须显式传入
- 若未启用 `checkpointer`，则不得声称支持 resume / history / 持久化恢复

当前代码状态：

- `workflow.py`：未传 `thread_id`
- `workflow_trace.py`：未传 `thread_id`
- `scripts/poc_phase4_hitl.py`：已传 `configurable.thread_id`

---

## 5. 与 trace / run_dir / approval record 的映射

### 5.1 设计原则

- `thread_id` 是主键
- `attempt_id` 是执行轮次索引
- `trace_dir` / `run_dir` / approval record 都是 `thread_id` 的派生索引，不可反向充当主键

### 5.2 推荐映射

```text
thread_id -> checkpoint history
thread_id + attempt_id -> trace_dir
thread_id + attempt_id -> run_dir
thread_id + review_step -> approval_record
thread_id + parent_checkpoint_id -> child_thread_id (fork)
```

### 5.3 当前仓库建议

- 保留现有 `workflow_trace_<timestamp>` 目录作为 `attempt_id` 维度
- 不把时间戳目录名提升为 thread 维度
- 正式接入 persistence 时，至少补一份可落盘的索引记录，明确：
  - `thread_id`
  - `attempt_id`
  - `trace_dir`
  - `final_state_json`
  - `approval_record_path`

---

## 6. resume 时必须保持不变的字段

以下字段在同一条恢复链上必须保持稳定：

- `configurable.thread_id`
- graph schema / 主链版本
- checkpointer namespace
- 运行模式（正式主链 or trace 主链）
- 已持久化的 state 与 checkpoint 指针

以下内容不应作为 resume 时重新提交的自由输入：

- 新的 `user_query`
- 新的 `retry_budget`
- 新的审批对象主键

恢复时应变化的通常只有：

- `Command(resume=...)` 的值
- 系统派生的 `attempt_id` / `resume_seq`

---

## 7. fork 语义

- 从历史 checkpoint fork 时，不应继续复用原 `thread_id`
- 应新建 `child_thread_id`
- 同时记录：
  - `parent_thread_id`
  - `source_checkpoint_id`
  - `fork_reason`

推荐格式：

```text
<parent_thread_id>-fork-<n>
```

---

## 8. checkpointer 接入时的最小配置要求

正式主链若要声称支持 `interrupt / resume / persistence`，至少同时满足：

1. `workflow.compile(checkpointer=...)`
2. `app.invoke(..., config={"configurable": {"thread_id": ...}})`
3. 有稳定的 `thread_id` 生成与复用方
4. 有可追踪的 approval record / trace 映射
5. 节点重放边界与幂等性已收口

当前尚未满足：

- 正式 backend 选型
- 正式入口传参
- 审批记录协议
- trace 与 thread 的索引关系

---

## 9. 当前裁决

### 9.1 已满足

- API 级 POC 已验证可行
- `thread_id` 在概念上已被证明是必需项
- `Phase6_副作用幂等性清单.md` 已补齐，能支撑下一步工程判断

### 9.2 未满足

- 正式主链传入 `thread_id`
- 正式主链接入 `checkpointer`
- trace / approval / checkpoint 的统一索引
- fork 分支的正式协议

### 9.3 阶段结论

- 对 Phase 7 正式主链化：`条件未满足`
- 对 Phase 7 开工前设计准备：`已满足`

