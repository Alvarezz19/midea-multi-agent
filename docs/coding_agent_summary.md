# 编码智能体 (Coding Agent) 当前工作流总结

> 最后更新: 2026-03-09

## 1. 概述

当前版本的 Coding Agent 是 LangGraph 工作流中的第四个节点，也是当前主链路里的最后一个业务节点。

它不负责 LLM 推理，也不负责业务理解或模块选择，而是把上游已经确定好的 execution_plan 和 retrieval_context 转换成平台可导入的最终 JSON 配置。

它的核心职责可以概括为：

1. 根据 execution_plan 中的逻辑节点与连接关系做实例化。
2. 从 retrieval_context 中取出对应模块的 template_json。
3. 为每个逻辑节点分配真实 ID、坐标、wires。
4. 将参数注入模板，输出最终 JSON 字符串。

也就是说，Coding Agent 本质上是一个确定性的“模板落地器”，而不是生成式智能体。

---

## 2. 在工作流中的位置

当前工作流主链路是：

```text
用户需求
  -> Analysis Agent
  -> Retrieval Agent
  -> Planning Agent
  -> Coding Agent
  -> END
```

对应 workflow.py 中与 Coding Agent 相关的边是：

```python
workflow.add_edge("planning", "coding")
workflow.add_edge("coding", END)
```

因此 Coding Agent 的直接上游是 Planning Agent，但它同时依赖 Retrieval Agent 留在状态里的 retrieval_context。

---

## 3. 相关文件

| 文件 | 作用 |
|:---|:---|
| agents/coding_agent.py | Coding Agent 主实现 |
| agents/coding_utils.py | 编码阶段的辅助工具集 |
| agents/planning_agent.py | 上游提供 execution_plan |
| agents/retrieval_agent.py | 上游提供 relevant_nodes 与 template_json |
| workflow.py | 编排 planning -> coding -> END |

---

## 4. 输入与输出

### 4.1 输入

Coding Agent 从共享状态中实际读取：

| 字段 | 类型 | 来源 | 说明 |
|:---|:---|:---|:---|
| execution_plan | dict | Planning Agent | PlanIR 序列化后的逻辑拓扑图 |
| retrieval_context | dict | Retrieval Agent | 检索到的模块完整定义，尤其是 template_json、ports_definition、parameters_schema |

其中 execution_plan 决定“要生成什么逻辑结构”，retrieval_context 决定“每种模块如何落地成平台 JSON”。

### 4.2 输出

Coding Agent 写回：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| generated_code | str | 最终平台 JSON 字符串 |
| current_step | str | coding_completed |

当前 generated_code 存储的是完整 JSON 文本，而不是 Python 代码。

---

## 5. Coding Agent 主流程

### 5.1 LangGraph 节点入口

__call__(state) 的执行顺序很简单：

1. 从 state 读取 execution_plan。
2. 从 state 读取 retrieval_context。
3. 调用 generate_json(execution_plan, retrieval_context)。
4. 将结果写入 state["generated_code"]。
5. 将 current_step 更新为 coding_completed。

### 5.2 generate_json() 总体流程

```text
execution_plan + retrieval_context
    │
    ▼
generate_json()
    │
    ├─ 1. 建立 module_type -> module_doc 映射
    ├─ 2. 为 logic_id 生成真实短 UUID
    ├─ 3. 根据连接关系计算自动布局坐标
    ├─ 4. 将连接转换为反向 wires 索引
    ├─ 5. 添加 tab 容器节点
    ├─ 6. 逐个节点读取 template_json 并填充
    ├─ 7. 序列化为 JSON 字符串
    └─ 8. 失败时返回“生成失败”tab 配置
```

---

## 6. 关键步骤详解

### 6.1 建立模块索引

Coding Agent 会先从 retrieval_context.relevant_nodes 构建：

```python
doc_map = {node['module_type']: node for node in relevant_nodes}
```

作用是通过 module_type 快速找到某个规划节点对应的：

1. template_json
2. ports_definition
3. parameters_schema
4. 模块原始名称

这也是为什么 Retrieval Agent 不能只返回模块摘要，必须保留完整模块定义。

### 6.2 逻辑 ID 实例化

Planning Agent 输出的是逻辑层标识 logic_id，例如 const_4_18、calc_temp_diff。Coding Agent 会把它们映射为真实短 UUID：

```python
id_map[node['logic_id']] = generate_short_uuid()
```

这样做的目的是把“逻辑拓扑设计”和“平台对象实例化”分开。

### 6.3 自动布局

Coding Agent 调用 topological_layout(nodes, connections) 自动计算坐标。其基本思想是：

1. 用连接关系构建有向图。
2. 通过拓扑层级确定横向位置。
3. 通过层内顺序确定纵向位置。

输出是：

```python
{logic_id: {"x": 100, "y": 100}}
```

### 6.4 反向连线索引

平台最终需要的是按输入端口组织的 wires 结构，而 execution_plan 中是 from -> to 的逻辑连接关系。

Coding Agent 通过 build_reverse_connections() 把它转换成：

```python
target_logic_id -> input_port_index -> {id: source_uuid, port: source_output_port}
```

然后在每个节点上构造：

```python
wires[input_port_index] = [{"id": "上游真实ID", "port": 上游输出端口}]
```

### 6.5 添加 Tab 容器

在真正生成功能节点前，Coding Agent 会先创建一个 tab 节点：

```json
{
  "id": "<flow_id>",
  "type": "tab",
  "label": "自动生成流程",
  "disabled": false,
  "info": ""
}
```

最终输出 JSON 的第一个元素就是这个容器节点。

### 6.6 逐个节点填充模板

对 execution_plan.nodes 中的每个节点，Coding Agent 会执行：

1. 从 doc_map 找到 module_doc。
2. 取出 template_json。
3. 如果 template_json 是列表，则取第一个元素作为模板。
4. 调用 resolve_input_count() 计算实际输入端口数量。
5. 构造 wires 数组。
6. 调用 fill_template() 注入 ID、坐标、参数、名称等信息。
7. 将结果追加到 final_modules。

如果 execution_plan 中引用的 module_type 在 doc_map 中不存在，当前实现会跳过该节点，而不是抛异常中断。

### 6.7 序列化与失败兜底

正常情况下，Coding Agent 会：

```python
json.dumps(final_modules, indent=2, ensure_ascii=False)
```

如果中途抛出异常，则不会让工作流直接崩溃，而是返回一个 disabled=true 的失败 tab 配置，info 中带错误信息。

---

## 7. 辅助函数体系

Coding Agent 的大部分关键细节都下沉在 coding_utils.py 中。

### 7.1 generate_short_uuid()

作用：生成 7 位短 ID，例如 b45d2af。

用途：

1. 节点实例 ID。
2. tab 容器 ID。

### 7.2 resolve_input_count(template_inputs, planned_params, module_doc)

作用：根据模板与规划参数确定节点的实际输入端口数量。

它支持多种模式：

1. {{inputs}} -> planned_params['inputs']
2. {{inputCount}} -> planned_params['inputCount']
3. {{inputsCount}} -> planned_params['inputsCount']
4. {{channelsPlusOne}} -> planned_params['channels'] + 1
5. 固定数值 -> 直接使用
6. 全部失败时 -> 从 ports_definition 中统计 always 条件端口数

这是 Coding Agent 能适配多类模块 schema 的关键函数。

### 7.3 topological_layout(nodes, connections)

作用：根据逻辑连接计算画布坐标。

当前实现特点：

1. 先构建邻接表与入度。
2. 用 BFS 风格拓扑遍历计算层级。
3. 以层级决定 X，以层内顺序决定 Y。
4. 对孤立节点默认放在第 0 层。

### 7.4 build_reverse_connections(connections, id_map)

作用：把逻辑连接变成平台 wires 所需的反向索引。

当前输出结构是：

```python
{
  "target_logic_id": {
    0: {"id": "source_uuid", "port": 0}
  }
}
```

### 7.5 fill_template(template, node, real_id, flow_id, coords, wires, module_name)

作用：把执行计划节点和运行期实例信息注入模板。

关键行为包括：

1. 写入 id、z、x、y、wires。
2. 将 node.parameters 覆盖到模板字段。
3. 兼容 user_defined_name，只把它作为 name 来源，而不写入最终 JSON。
4. 根据模板 inputs 占位符处理 inputs 映射。
5. 特殊处理 channelsPlusOne。
6. 若规划侧未提供 name，则使用模块原始名称兜底。
7. 最后递归清理未替换的 {{placeholder}} 字段。

### 7.6 clean_placeholders(obj)

作用：递归删除模板中残留的未替换占位符字段，保证输出 JSON 不含 {{...}} 模板变量。

---

## 8. 输入端口解析设计背景

不同模块模板对输入端口数量的表达方式并不统一，这是 Coding Agent 最容易出错的地方之一。

常见模式包括：

```text
{{inputs}}
{{inputCount}}
{{inputsCount}}
{{channelsPlusOne}}
固定数值
```

因此当前实现采用的策略不是写死某一种参数名，而是：

1. 优先读取模板占位符本身引用的参数名。
2. 特殊处理 channelsPlusOne。
3. 再尝试 inputCount / inputsCount / inputs 等常见别名。
4. 最后从 ports_definition 做兜底推断。

这使得 Coding Agent 能兼容不同类别模块的 schema 差异，而不用为每个模块单独写分支。

---

## 9. 错误处理与边界行为

| 场景 | 当前处理方式 |
|:---|:---|
| execution_plan 为空 | 仍会生成至少一个 tab 节点的 JSON |
| retrieval_context 中缺少某个 module_type | 跳过该节点，继续处理其他节点 |
| template_json 是空列表 | 退化为空模板 |
| template_json 是列表 | 取第一个模板元素 |
| 生成过程抛异常 | 返回 disabled=true 的失败 tab 配置 |
| 模板残留未替换占位符 | clean_placeholders() 递归删除 |

这里需要注意一个实现特征：Coding Agent 本身不会再次验证 execution_plan 的逻辑正确性，它默认上游 Planning Agent 已完成结构校验。它更关注“如何落地生成”，而不是“规划是否合理”。

---

## 10. 与上下游智能体的协作关系

### 10.1 与 Planning Agent

Planning Agent 提供 execution_plan，定义：

1. 用哪些模块。
2. 每个模块的参数是什么。
3. 节点之间怎么连接。

Coding Agent 不重新规划，只把这些逻辑关系实例化成平台对象。

### 10.2 与 Retrieval Agent

Retrieval Agent 提供 relevant_nodes，决定：

1. 每种 module_type 的 template_json。
2. 端口定义 ports_definition。
3. 参数结构 parameters_schema。
4. 模块名称等元信息。

没有 retrieval_context，Coding Agent 无法把 execution_plan 可靠地翻译成最终 JSON。

### 10.3 与 Analysis Agent

Coding Agent 不直接读取 analysis_result，也不参与业务理解。Analysis Agent 的影响已经在 Planning Agent 阶段被吸收进 execution_plan 里了。

---

## 11. 当前版本相对旧认知的几个要点

以下理解在当前版本里更准确：

1. Coding Agent 处理的是 JSON 配置生成，不是 Python 代码生成。
2. 它依赖的是 execution_plan + retrieval_context，而不是单独依赖 planning 输出。
3. 它位于 analysis -> retrieval -> planning 之后，而不是一个脱离完整工作流的独立转换器。
4. fill_template() 已对 user_defined_name 做了兼容处理，不会把该字段原样落入最终平台 JSON。
5. Coding Agent 的失败兜底是返回失败 tab，而不是抛异常终止整个工作流。

---

## 12. 小结

当前版本的 Coding Agent 是整个工作流里的“确定性落地层”。

它的核心设计可以概括为：

1. 上游规划负责逻辑。
2. 检索上下文负责模板和规格。
3. Coding Agent 负责实例化、布局、连线转换和模板填充。
4. 通过 resolve_input_count、fill_template、clean_placeholders 等工具适配不同模块 schema。

这使得系统能够把“业务理解 -> 模块检索 -> 逻辑规划”的结果，最终稳定地转成可导入平台的 JSON 组态文件。