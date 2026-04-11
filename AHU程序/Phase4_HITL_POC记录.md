# Phase 4 HITL / interrupt / persistence POC 记录

> 日期：2026-04-11  
> 状态：POC，未接入正式主链  
> 对应脚本：`scripts/poc_phase4_hitl.py`

## 1. 目标

本 POC 只验证 4 件事：

1. 当前 LangGraph 版本下，`checkpointer + thread_id` 能驱动可恢复执行。
2. `interrupt -> Command(resume=...)` 的恢复路径在本地环境可重复运行。
3. `get_state / get_state_history` 能用于暂停态与历史检查。
4. 以上能力可以独立演示，不需要改动正式 `workflow.py` / `workflow_trace.py`。

## 2. 设计选择

- checkpointer：使用 `InMemorySaver`
- graph 规模：独立最小图 `prepare_request -> human_review -> apply_patch/abort`
- HITL 入口：`human_review` 节点内调用 `interrupt(...)`
- 恢复方式：`graph.invoke(Command(resume=...), config)`
- 检查方式：
  - `graph.get_state(config)` 查看暂停态与完成态
  - `graph.get_state_history(config)` 查看完整 checkpoint 历史
  - `graph.update_state(before_review.config, ...)` 从历史 checkpoint fork 一条新分支

以上做法与 LangGraph 官方文档约束一致：

- durable execution 依赖 checkpointer
- 执行配置中必须提供 `thread_id`
- 恢复会从 checkpoint 对应节点起点重放，不是从 Python 某一行继续
- `interrupt` 与 `Command(resume=...)` 适合做独立 HITL POC，再决定是否进入正式主链

## 3. 运行命令

```powershell
conda activate midea

python scripts/poc_phase4_hitl.py
```

可选参数：

```powershell
conda activate midea

python scripts/poc_phase4_hitl.py --thread-id phase4-hitl-demo-2 --resume reject
```

## 4. 预期输出

脚本会按顺序打印：

1. 首次 `invoke` 命中 `interrupt` 后的返回值
2. `get_state` 读取到的暂停态 checkpoint
3. `Command(resume=...)` 恢复后的完成态结果
4. `get_state` 读取到的完成态 checkpoint
5. `get_state_history` 列出的历史快照
6. 从 `human_review` 之前的 checkpoint fork 一条新分支并再次恢复

重点观察点：

- 首次执行结果中会带 `__interrupt__`
- 暂停态的 `next` 应指向 `human_review`
- 恢复后结果会落到 `apply_patch` 或 `abort`
- 历史快照中能看到 `prepare_request -> human_review -> apply_patch/abort -> END`
- fork 后的新分支会再次在 `human_review` 处暂停，并可用新的 `Command(resume=...)` 继续

## 5. 本地结论

在当前环境中，以下能力可用：

- `langgraph.checkpoint.memory.InMemorySaver`
- `langgraph.types.interrupt`
- `langgraph.types.Command`
- `graph.get_state(...)`
- `graph.get_state_history(...)`
- `graph.update_state(...)`

因此，Phase 4 后续如果要进入正式 HITL 设计，至少 API 级别不存在阻塞。

## 6. 为什么仍然不接入正式主链

当前不入主链的原因不是“API 不可用”，而是正式链路还有 3 个工程约束没做完：

1. 持久化介质还未选型。
当前只用 `InMemorySaver` 做开发态演示，进程结束后状态即消失。

2. 正式节点副作用还没全面梳理幂等性。
官方文档明确说明恢复会重放节点起点，若未来在节点里加入外部写操作，需要先把副作用包进 task 或改成幂等调用。

3. 线程管理与人工审批协议尚未定稿。
正式接入后，需要定义谁生成 `thread_id`、审批消息如何落库、超时与取消如何处理。

## 7. 依赖评估

- 本 POC 不需要新增依赖，也不需要修改 `requirements.txt`
- 若后续改用 sqlite / postgres checkpointer，再单独评估依赖与运行时基线

## 8. 建议下一步

1. 继续保持正式主链无 checkpointer，先把 Repair 与并行派发收口。
2. 等 `Send` fan-out 与 Repair 路由稳定后，再设计正式 HITL 节点插入点。
3. 若进入正式 persistence 方案，优先补“副作用幂等性清单”和“thread_id 管理约定”。
