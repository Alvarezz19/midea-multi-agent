# Phase 6 副作用幂等性清单

> 更新时间：2026-04-17  
> 目标：在不改正式主链拓扑的前提下，为下一阶段评估 `Send / HITL / persistence` 提供节点级副作用与幂等性边界。  
> 依据：当前代码实现、`AHU程序/Phase4_Send并行预留设计.md`、`AHU程序/Phase4_HITL_POC记录.md`，以及 LangGraph 官方文档：  
> - <https://docs.langchain.com/oss/python/langgraph/use-graph-api>  
> - <https://docs.langchain.com/oss/python/langgraph/durable-execution>  
> - <https://docs.langchain.com/oss/python/langgraph/interrupts>

---

## 1. 当前收口结论

- 当前正式主链仍未接入 `checkpointer`、`thread_id`、`interrupt`；本清单是 Phase 7 准入资料，不代表已允许主链化。
- 适合保持普通纯计算节点的主要是：`architecture_planning`、`subsystem_planning`、`global_assembly`、`verification`、`repair_router`。
- 需要优先明确 durable execution 边界的主要是：`analysis`、`retrieval`、`coding`、`repair_agent`，以及图外的 `workflow_trace` 落盘逻辑。
- 若后续进入正式 HITL，最自然的切入点不是直接把 `interrupt` 塞进现有节点中间，而是把“生成候选结果”和“真正应用 patch / 外部写入”拆开。

---

## 2. 节点级清单

| 节点/模块 | 外部依赖 | 是否近似纯函数 | 当前副作用/非确定性 | durable execution 建议 | 当前判断 |
| --- | --- | --- | --- | --- | --- |
| `analysis` | LLM | 否 | 模型输出可能波动；失败时有 fallback，但主路径仍依赖在线/本地模型调用 | 把 LLM 调用封成独立 task；规范化与 `build_requirement_spec` 保留在纯节点 | 进入 HITL / persistence 前需先收口 |
| `retrieval` | Chroma / embedding / pattern library | 否 | 召回结果受向量库内容、排序分数和 query variant 影响；重放时可能随资产变化漂移 | 至少把 atomic / subflow / pattern 三路查询边界独立出来；明确“重放使用同一资产快照”的要求 | 进入 durable execution 前需先收口 |
| `architecture_planning` | 无 | 是 | 规则打分与结构投影，当前未见时间/随机数依赖 | 可继续作为普通节点，无需优先拆 task | 当前可保留 |
| `subsystem_planning` | 无 | 是 | 顺序规划本身是纯内存构造；未来若接 `Send`，并发风险主要来自状态写入边界而非副作用 | 继续保持纯计算；并行化时只允许 worker 返回单个 `subsystem_id` 的 state update | 当前可保留 |
| `global_assembly` | 无 | 是 | 纯内存装配全局 IR | 可继续作为普通节点；不建议拆分成副作用型 task | 当前可保留 |
| `coding` | 无外部 I/O，但内部使用 UUID | 否 | 当前 ID 分配含随机 UUID，重放后产物 ID 可能变化 | 优先改成稳定 ID 映射；若暂时不改，至少把 ID 分配边界独立并明确同 run 复用策略 | Phase 7 前的关键阻塞项 |
| `verification` | 无 | 是 | 纯结构验收与 issue 归纳 | 可继续作为普通节点 | 当前可保留 |
| `repair_router` | 无 | 是 | 基于验收结果和预算裁决，未见外部副作用 | 可继续作为普通节点 | 当前可保留 |
| `repair_agent` | 无外部 I/O，但会修改主状态 | 条件成立时近似纯函数 | 会递增重试计数、写 `repair_context / repair_history / route_decision` 并 patch 上游主对象；若未来插入 HITL，节点中途暂停会放大重放影响 | 若引入 HITL，建议拆成 `prepare_patch -> human_review -> apply_patch` 三段 | Phase 7 前需先拆边界 |
| `workflow_trace`（图外） | 文件系统 / 当前时间 | 否 | 每次运行按当前时间创建目录并落盘 JSON/Markdown/final state | 建议改成 `thread_id + attempt_id` 关联策略，避免 resume 多次生成不可追踪目录 | Phase 7 前需先收口 |

---

## 3. 当前最需要补的幂等边界

### 3.1 `analysis`

- 当前主风险不是状态写冲突，而是 LLM 输出波动。
- 进入 durable execution 前，应把“模型调用”与“结果规范化”分离。
- `interrupt` 若未来出现在 analysis 之后，恢复时应尽量不重复调用模型。

### 3.2 `retrieval`

- 当前主风险是资产和索引状态可能变化，导致同一 query 在不同时间命中不同结果。
- 进入 durable execution 前，应明确：
  - 是否要求同一 `thread_id` 恢复时绑定同一 persist dir / collection 版本
  - 是否要求回放使用同一批 query variants
  - 是否把 `selected_case_pattern_id`、top-N IDs 和分数视为恢复证据

### 3.3 `coding`

- 当前是最明显的确定性阻塞点。
- 若未来恢复从 `coding` 节点起点重放，而内部继续使用随机 UUID，编译结果的对象 ID 会漂移。
- 在 Phase 7 之前，至少需要二选一：
  - 改成稳定 ID 生成策略
  - 或把 ID 分配与编译产物固化做成可复用 task

### 3.4 `repair_agent`

- 当前 repair 流程把“算 patch”“递增计数”“应用 patch”“记录历史”放在同一个节点里。
- 若未来在 repair 过程中插入人工审批，直接在这个节点内部 `interrupt` 会让恢复时重复跑前置逻辑。
- 更稳的做法是拆成：
  - `prepare_repair_patch`
  - `human_review`
  - `apply_repair_patch`

### 3.5 `workflow_trace`

- 当前 trace 目录名基于时间戳，适合 attempt 维度，不适合 thread 维度。
- 若未来支持 resume / replay，应至少补：
  - `thread_id -> trace_dir[]`
  - `thread_id + attempt_id -> final_state`
  - `approval_record -> trace_dir`

---

## 4. 当前可直接沿用的纯计算节点

以下节点当前主要做内存对象投影、规则校验或结构组装，进入 Phase 7 时不应优先拆成 task：

- `architecture_planning`
- `subsystem_planning`
- `global_assembly`
- `verification`
- `repair_router`

原因：

- 当前没有显式外部写操作。
- 主要依赖已进入 state 的输入对象。
- 即使未来引入 persistence，它们的主要风险仍然是上游输入是否稳定，而不是自身副作用。

---

## 5. 与 `Send` 并行的关系

- 本清单只关注副作用与幂等性，不直接替代 reducer 设计。
- 对 `Send` 来说，真正敏感的不是“节点是否纯函数”，而是“并行 worker 是否会同时写同一状态键”。
- 相关 reducer 风险与合并策略，以 `subsystem_plan_map`、`parallel_merge_conflicts` 为核心，详见 `AHU程序/Phase6_Send_HITL准入评审表.md`。

---

## 6. 当前裁决

- 对正式主链接入 `persistence / interrupt / HITL`：`未满足`
- 对下一阶段继续推进准备工作：`已满足`

仍缺的关键条件：

1. 正式 `checkpointer` 方案
2. `thread_id` 生命周期契约
3. `coding` 的稳定 ID 或等价幂等边界
4. `repair_agent` 的 HITL 可拆分边界
5. `workflow_trace` 的 thread/attempt 映射规则
