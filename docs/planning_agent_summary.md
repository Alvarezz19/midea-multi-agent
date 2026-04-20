# PlanningAgent 当前状态说明

> 最后更新：2026-04-20

## 1. 先说结论

`agents/planning_agent.py` 已经不是当前正式主链里的规划节点，而且当前文件只剩 compat wrapper。

真实实现已迁移到：

```text
agents/legacy/planning_agent.py
```

当前正式主链使用的是：

```text
analysis
  -> retrieval
  -> architecture_planning
  -> subsystem_planning
  -> global_assembly
```

也就是说，旧 `PlanningAgent` 现在的定位是：

- 旧主链 compat planner
- 历史 `execution_plan` 语义保留实现
- 仍被 Phase 2 compat 测试覆盖

## 2. 它为什么还保留

当前仓库里仍有两类路径需要它：

1. Phase 2 / compat 回归测试，验证旧 `execution_plan` 语义没有完全失效
2. 仍消费 legacy `retrieval_context` 或 `execution_plan` 的历史调用方

因此它不是“死代码”，但也不是“正式主链节点”；现在更准确地说，它是“已经显式归档到 legacy 目录、但仍有 compat 测试覆盖的旧 planner”。

## 3. 当前输入输出

### 输入

- `user_query`
- `retrieval_bundle`（优先）
- `retrieval_context`（兼容）
- `analysis_result`

### 输出

- `execution_plan`
- `current_step = "planning_completed"`

这里的 `execution_plan` 只代表旧 PlanIR 语义，不是当前 Phase 3 编译链的真实规划主产物。

## 4. 与 Phase 3 的关系

Phase 3 把原来的单体规划链拆成三层：

1. `ArchitecturePlanner`：系统骨架、页面、共享信号、模板偏好
2. `SubsystemPlanner`：每个子系统的局部 IR
3. `GlobalAssembler`：把局部 IR 组装为全局 `assembled_graph_ir`

因此：

- `PlanningAgent` 不再负责正式系统级规划
- `execution_plan` 不再是正式主链中的真实输入
- `assembled_graph_ir` 才是当前编译器与验收器的真实输入边界

## 5. 当前测试覆盖

旧 `PlanningAgent` 仍有自动化覆盖，主要集中在：

- `tests/test_phase2_planning_bundle.py`
- `tests/test_phase2_bundle_consumers.py`

这意味着当前仓库仍然把它视为“兼容层需要维护的模块”，而不是可以直接删掉的历史文件。

## 6. 后续处理建议

当前最合适的定位是：

- 继续保留 legacy 实现
- 旧路径仅保留兼容 wrapper
- 不再把它写成正式主链节点
- 等 compat 调用方与 compat 测试进一步收缩后，再决定是否彻底删除 wrapper

## 7. 一句话结论

`PlanningAgent` 现在是“真实实现已迁移到 `agents/legacy/`、旧路径仅保留 wrapper 的 compat planner”，不是当前 Phase 3 正式规划节点。
