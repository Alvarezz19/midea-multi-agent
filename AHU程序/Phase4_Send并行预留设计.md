# Phase 4 Send 并行预留设计

> 日期：2026-04-11  
> 状态：设计预留 + Phase 7 独立试点已验证，当前仍不改正式主链行为  
> 目标：为后续把 `subsystem_planning` 从顺序执行升级为 LangGraph `Send` fan-out 做好可直接落地的接口设计。

> 2026-04-17 补充：`scripts/poc_phase7_send_parallel.py` 与 `tests/test_phase7_send_reducer_contract.py` 已按本设计在独立测试图中验证以下合同：`subsystem_plan_map` 按 `subsystem_id` merge、`parallel_merge_conflicts` append-only、worker 只返回局部 state update、重复 `subsystem_id` fail-fast、稳定排序遵循 `dispatch_index -> subsystem_id`。正式主链仍未切换。

## 1. 设计边界

- 当前正式主链继续保持顺序版 `subsystem_planning`，本文件只定义未来并行化的输入、状态约束、冲突处理和稳定排序。
- 依据 LangGraph 官方 Graph API，`Send` 适合 map-reduce 风格 fan-out；多个分支并发写同一状态键时，必须为该键提供 reducer。
- 当前 Repair 闭环已经要求修补上游真实主对象；未来并行版也沿用同一约束，不允许 worker 只写会被下游重算覆盖的派生产物。

## 2. 未来 Fan-out 拓扑

目标拓扑：

```text
architecture_planning
  -> subsystem_dispatcher
  -> Send(subsystem_planning_worker for each subsystem)
  -> subsystem_merge
  -> global_assembly
```

说明：

- `subsystem_dispatcher` 只负责按 `planning_order` 生成并行任务，不做真实规划。
- 每个 `subsystem_planning_worker` 只拥有单个 `subsystem_id` 的写权限。
- `subsystem_merge` 负责冲突检测、稳定排序、产出正式 `subsystem_plan_map`。
- 若 `repair_scope == planning` 且只影响部分子系统，后续可只重派受影响的 `subsystem_id` 子集。

## 3. Send 输入结构

建议把 fan-out payload 收紧为如下结构：

```python
from typing_extensions import TypedDict


class SubsystemPlanningDispatch(TypedDict, total=False):
    subsystem_id: str
    dispatch_index: int
    page_id: str
    requirement_spec: dict
    subsystem_descriptor: dict
    architecture_plan: dict
    retrieval_bundle: dict
    repair_context: dict
    upstream_shared_signal_registry: list[dict]
```

字段约束：

- `subsystem_id`：唯一主键，worker 只能写自己名下的子系统结果。
- `dispatch_index`：由 `planning_order` 映射得到，后续 merge 只认这个排序键，不认异步完成先后。
- `subsystem_descriptor`：来自 `decomposition_result.subsystem_descriptors[*]` 的单条切片。
- `upstream_shared_signal_registry`：用于并行 worker 读取共享信号归属，但 worker 不直接改全局 registry。
- `repair_context`：仅在 repair 回跳时透传，用于局部重派受影响分支。

推荐的 dispatcher 伪代码：

```python
def build_subsystem_dispatches(state) -> list[Send]:
    order = state["decomposition_result"]["planning_order"]
    descriptor_map = {
        item["subsystem_id"]: item
        for item in state["decomposition_result"]["subsystem_descriptors"]
    }
    sends = []
    for dispatch_index, subsystem_id in enumerate(order):
        descriptor = descriptor_map[subsystem_id]
        payload = {
            "subsystem_id": subsystem_id,
            "dispatch_index": dispatch_index,
            "page_id": descriptor.get("page_id", ""),
            "requirement_spec": state["requirement_spec"],
            "subsystem_descriptor": descriptor,
            "architecture_plan": state["architecture_plan"],
            "retrieval_bundle": state["retrieval_bundle"],
            "repair_context": state.get("repair_context", {}),
            "upstream_shared_signal_registry": state["architecture_plan"].get("shared_signal_registry", []),
        }
        sends.append(Send("subsystem_planning_worker", payload))
    return sends
```

## 4. Reducer 设计

### 4.1 正式状态预留

未来建议把状态扩成：

```python
from typing import Annotated


class WorkflowState(TypedDict):
    subsystem_plan_map: Annotated[dict[str, dict], merge_subsystem_plan_map]
    parallel_merge_conflicts: Annotated[list[dict], merge_parallel_conflicts]
```

说明：

- `subsystem_plan_map` 是正式 fan-in 结果。
- `parallel_merge_conflicts` 用于记录 reducer 或 fan-in 发现的冲突，不允许静默覆盖。

### 4.2 `subsystem_plan_map` reducer

推荐 reducer 语义：

```python
def merge_subsystem_plan_map(
    current: dict[str, dict],
    update: dict[str, dict],
) -> dict[str, dict]:
    merged = dict(current or {})
    for subsystem_id, plan in (update or {}).items():
        if subsystem_id in merged:
            raise ValueError(f"duplicate_subsystem_id:{subsystem_id}")
        merged[subsystem_id] = plan
    return merged
```

设计结论：

- 同一 `subsystem_id` 被重复写入时，直接 hard reject，不允许 `last-write-wins`。
- worker 输出必须只包含一个 key，即自己的 `subsystem_id`。
- reducer 只负责唯一键累积，不负责业务语义冲突裁决。

### 4.3 冲突 reducer

```python
def merge_parallel_conflicts(
    current: list[dict],
    update: list[dict],
) -> list[dict]:
    return list(current or []) + list(update or [])
```

该列表由 `subsystem_merge` 和后续 `global_assembly` 共同消费。

## 5. Fan-in 冲突规则

`subsystem_merge` 统一做以下 deterministic 检查：

### 5.1 同名 signal 冲突

- 场景：两个子系统都声称导出同一个共享信号，且没有上游 registry 显式允许多导出方。
- 处理：写入 `parallel_merge_conflicts`，冲突类型为 `parallel_shared_signal_conflict`，并 reject。
- 不允许策略：静默选择第一个完成的分支。

建议冲突记录：

```json
{
  "type": "parallel_shared_signal_conflict",
  "signal_name": "supply_fan_available_flag",
  "exporters": ["supply_fan_ctrl", "heater_ctrl"],
  "resolution": "reject"
}
```

### 5.2 同页签布局冲突

- 场景：两个子系统在同一页签占用了相同布局锚点，或都要求固定坐标但彼此重叠。
- 处理：写入 `parallel_merge_conflicts`，冲突类型为 `parallel_layout_conflict`。
- 第一版策略：不在 reducer 内抢修，交给 `subsystem_merge` reject，后续再决定是否交给 layout repair。

### 5.3 重复 `subsystem_id`

- 场景：dispatcher 错误或 repair 重派时重复派发同一子系统。
- 处理：由 `merge_subsystem_plan_map` 直接抛出 `duplicate_subsystem_id:*`，视为图构建错误。
- 原因：这个问题不是业务层冲突，而是 fan-out 编排错误，应该 fail fast。

## 6. 稳定排序规则

并行结果必须可重放、可比较，不能依赖异步返回顺序。

排序规则定死为：

1. 先按 `dispatch_index` 升序。
2. 若 `dispatch_index` 相同，按 `subsystem_id` 字典序。
3. `subsystem_merge` 输出正式 `subsystem_plan_map` 时，按上述顺序重建 dict 插入顺序。

实现要求：

- dispatcher 必须总是从 `planning_order` 生成稳定的 `dispatch_index`。
- worker 输出中必须保留 `_dispatch_index` 或等价 metadata，供 merge 使用。
- 下游测试断言只能基于排序后结果，不读取“谁先完成”。

## 7. 与 Repair 的关系

- `planning` scope repair 不直接修 `subsystem_plan_map`，而是修 `architecture_plan / decomposition_result` 后重新派发受影响子系统。
- `assembly` scope repair 仍修 `subsystem_plan_map`，但未来如果分支并行执行，修复后只需回跳 `subsystem_merge -> global_assembly`，不必重跑全部 worker。
- `compile` scope repair 仍直接修 `assembled_graph_ir`，与 `Send` 并行化无直接耦合。

## 8. 建议实现顺序

1. 新增 `subsystem_dispatcher` 与单子系统 worker 节点，但先在测试图里验证。
2. 为 `subsystem_plan_map` 与冲突列表加 `Annotated[..., reducer]`。
3. 落地 `subsystem_merge` 并建立冲突负测。
4. 最后把正式主链从顺序版 `subsystem_planning` 切到 `Send` fan-out。

## 9. 收口结论

- 当前不改正式行为；顺序版仍是最稳妥的主链。
- 真正进入并行化时，核心不是“把顺序循环改成 `Send`”，而是先保证：
  - fan-out 输入稳定
  - reducer 不静默覆盖
  - fan-in 冲突 deterministic reject
  - 最终 `subsystem_plan_map` 顺序稳定
- 以上约束已经足够直接转实现，不需要再补关键决策。
