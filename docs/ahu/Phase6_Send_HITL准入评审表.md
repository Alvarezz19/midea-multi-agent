# Phase 6 Send / HITL 准入评审表

> 更新时间：2026-04-17  
> 用途：在进入 Phase 7 之前，对 `Send` 并行和 `HITL / persistence` 主链化做统一裁决。  
> 裁决口径：`go / no-go / conditional-go`

---

## 1. 当前总裁决

- `Send` 并行主链化：`conditional-go`
- `HITL / persistence` 主链化：`no-go`
- 合并总裁决：`conditional-go`

解释：

- `Send` 方向的 reducer 风险、冲突规则和稳定排序规则已经具备正式设计基础，但还未把 reducer state keys 真正入链，也未把顺序节点改成“只返回局部 state update”。
- `HITL / persistence` 方向已有 POC，但正式主链仍无 `checkpointer`、无 `thread_id` 入口、无审批协议，也未完全收口 durable execution 所需的幂等边界。

---

## 2. 证据清单

- `docs/ahu/Phase4_Send并行预留设计.md`
- `docs/ahu/Phase4_HITL_POC记录.md`
- `docs/ahu/Phase6_副作用幂等性清单.md`
- `docs/ahu/Phase6_thread_id与恢复契约.md`
- `workflow.py`
- `workflow_trace.py`
- `scripts/poc_phase4_hitl.py`

---

## 3. Send 并行 readiness

| 裁决项 | 当前状态 | 结论 | 说明 |
| --- | --- | --- | --- |
| 是否已有 `Send` fan-out 拓扑草案 | 已有 | 通过 | 已明确 `subsystem_dispatcher -> worker -> subsystem_merge` |
| 是否已有 reducer state keys 清单 | 已有 | 通过 | 当前核心是 `subsystem_plan_map` 与新增 `parallel_merge_conflicts` |
| 是否已有并行冲突规则 | 已有 | 通过 | 已定义共享信号冲突、布局冲突、重复派发 fail-fast |
| 是否已有稳定排序规则 | 已有 | 通过 | 已明确 `dispatch_index -> subsystem_id` |
| 正式主链状态是否已改成 `Annotated[..., reducer]` | 尚未 | 未通过 | `workflow.py` / `workflow_trace.py` 仍是普通 `TypedDict` |
| 节点是否已改成只返回局部 state update | 尚未 | 未通过 | 当前大量节点仍是原地改 `state` 后返回整份 state |
| trace 版是否考虑并行节点记录顺序 | 尚未 | 未通过 | `workflow_trace.py` 的 `node_io_records` 仍是顺序 append 假设 |

### Send 分项结论

- 设计准备：`已满足`
- 正式主链切换：`未满足`

---

## 4. HITL / persistence readiness

| 裁决项 | 当前状态 | 结论 | 说明 |
| --- | --- | --- | --- |
| 是否已有最小 POC | 已有 | 通过 | `InMemorySaver + thread_id + interrupt + Command(resume=...)` 已跑通 |
| 是否已有正式 `checkpointer` 方案 | 尚未 | 未通过 | 仅有 POC 内存方案 |
| 是否已有 `thread_id` 生命周期约定 | 已有文档 | 条件通过 | 仅文档收口，正式入口尚未实现 |
| 是否已有审批记录 / trace 映射规则 | 已有文档 | 条件通过 | 仍未落到正式代码 |
| 是否已有副作用幂等性结论 | 已有 | 通过 | 已形成节点级清单 |
| 是否已有 durable execution 的关键阻塞识别 | 已有 | 通过 | 主要阻塞点是 `analysis`、`retrieval`、`coding`、`repair_agent`、`workflow_trace` |
| 正式主链是否已传 `configurable.thread_id` | 尚未 | 未通过 | `workflow.py` / `workflow_trace.py` 仍未支持 |
| 正式主链是否已接 `interrupt` 节点 | 尚未 | 未通过 | 只有独立 POC 使用 `interrupt` |

### HITL / persistence 分项结论

- POC 能力验证：`已满足`
- 正式主链接入：`未满足`

---

## 5. 当前 reducer state keys 裁决

| 状态键 | 当前建议 | 结论 |
| --- | --- | --- |
| `subsystem_plan_map` | 需要 reducer；按 `subsystem_id` 唯一键并集，重复 key 直接 fail | 通过 |
| `parallel_merge_conflicts` | 需要新增；append-only reducer | 通过 |
| `debug_history` | 仅当未来明确开放并发调试日志时才考虑 reducer | 暂不纳入 |
| `architecture_plan` / `decomposition_result` | 保持单写 | 通过 |
| `repair_context` / `repair_history` / `route_decision` | 保持单写 | 通过 |
| `assembled_graph_ir` / `compiled_artifact` / `verification_report` | 保持单写 | 通过 |

---

## 6. 当前 durable execution 阻塞项

| 项目 | 当前状态 | 处理建议 |
| --- | --- | --- |
| `analysis` LLM 调用 | 非确定性 | 拆 task，规范化逻辑留在纯节点 |
| `retrieval` 外部查询 | 依赖外部索引状态 | 拆 query 边界，绑定资产快照口径 |
| `coding` UUID 生成 | 非确定性 | 改稳定 ID 或明确 task 边界 |
| `repair_agent` 节点过厚 | 未来插 HITL 会重放前置逻辑 | 拆成 prepare/review/apply |
| `workflow_trace` 时间戳落盘 | resume 后 attempt 无稳定映射 | 引入 `thread_id + attempt_id` 索引 |

---

## 7. 进入 Go 前必须同时满足的条件

1. `workflow.py` 与 `workflow_trace.py` 同步补齐正式 `checkpointer` 方案
2. 正式入口支持 `thread_id`
3. reducer state keys 入链，且 trace 版行为同步
4. `subsystem_planning` 并行 worker 只返回局部 state update
5. `coding` 的确定性重放边界收口
6. `repair_agent` 的 HITL 可拆分边界收口
7. trace / approval / checkpoint 索引方案落地

---

## 8. 本轮裁决结论

### 8.1 可以直接进入下一轮继续做的事

- 按照本评审表和 Phase 6 文档，继续做 Phase 7 的工程设计与最小代码改造
- 把 `Send` 的 reducer 和 worker 返回 schema 先在测试图里落地
- 把 `thread_id`、`attempt_id`、trace 映射先做成正式输入协议

### 8.2 当前不该直接做的事

- 直接把正式主链切到 `Send`
- 直接把 `interrupt / checkpointer / persistence` 接进正式主链
- 在未处理 `coding` 非确定性和 `repair_agent` 边界前就做正式 resume

### 8.3 最终结论

- 作为 Phase 7 开工前的设计准入：`conditional-go`
- 作为当前时点的正式主链准入：`no-go`

