# 编码智能体 (Coding Agent) 当前工作流总结

> 最后更新：2026-04-07

## 1. 当前定位

当前版本的 `CodingAgent` 已经不是“接收 `execution_plan` 直接出 JSON”的节点。

在 Phase 3 主链里，它的真实职责是：

1. 消费 `GlobalAssembler` 产出的 `assembled_graph_ir`
2. 结合 `retrieval_bundle` / `retrieval_context` 中的模板定义
3. 以确定性方式编译出平台 JSON 与 `compiled_artifact`

也就是说，它本质上是确定性编译器，而不是规划器或生成式智能体。

## 2. 在工作流中的位置

当前正式主链是：

```text
user_query
  -> analysis
  -> retrieval
  -> architecture_planning
  -> subsystem_planning
  -> global_assembly
  -> coding
  -> verification
  -> END
```

`CodingAgent` 的直接上游是 `global_assembly`，下游是 `verification`。

## 3. 真实输入与输出

`CodingAgent` 从共享状态中读取：

- `assembled_graph_ir`
- `retrieval_bundle`（优先）或 `retrieval_context`（兼容）

它写回：

- `compiled_artifact`
- `generated_code`
- `current_step = "coding_completed"`

其中：

- `compiled_artifact` 是真实主产物
- `generated_code` 只是兼容字段，值等于 `compiled_artifact["json_text"]`

## 4. 当前边界

`CodingAgent` 当前负责：

- tab / subflow / node 实例化
- 模板填充
- ID 分配
- wires 反向映射
- 编译报告生成

`CodingAgent` 当前不负责：

- 自然语言理解
- 系统级规划
- 子系统拆解
- 自动修复

## 5. 与 Phase 3 的关系

Phase 3 引入了 `ArchitecturePlanner`、`SubsystemPlanner`、`GlobalAssembler`，但没有改变 `CodingAgent` 的核心边界。

真正发生变化的是：

- `execution_plan` 不再是 `CodingAgent` 的正式输入
- `assembled_graph_ir` 仍然是 `CodingAgent` 的唯一真实编译输入
- `GlobalAssembler` 会回填兼容 `execution_plan`，供旧接口、历史观察与 compat 路径继续使用
- `VerifierAgent` 已可直接消费 `Phase 3` 原生产物，不再把 `execution_plan` 当作验收硬依赖

## 6. 当前结论

如果只保留一句话来理解当前 `CodingAgent`：

> 它是 Phase 3 分层规划主链里的确定性编译层，负责把 `assembled_graph_ir` 稳定落地为平台 JSON，而不是负责理解需求或决定系统结构。
