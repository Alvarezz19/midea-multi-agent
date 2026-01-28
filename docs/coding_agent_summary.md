# 编码智能体 (Coding Agent) 工作流总结

## 1. 智能体结构与职责

**Coding Agent** 是系统中的“执行工匠”，负责将抽象的逻辑规划（逻辑ID、拓扑图）落地为详细的、平台可执行的 JSON 配置文件。它不涉及 LLM 推理，而是使用确定性算法进行数据映射和模板填充。

### 核心组成
*   **CodingAgent 类**: 核心协调器，串联整个编码流程。
*   **辅助工具集 (`coding_utils`)**: 包含 `topological_layout`（自动布局）、`build_reverse_connections`（连线转换）、`fill_template`（参数注入）等独立函数。

---

## 2. 输入与输出

### 输入 (Input)
*   **执行计划 (`plan_ir`)**: 规划智能体输出的中间表示 (`PlanIR` 字典)，包含逻辑节点和连接。
*   **检索上下文 (`retrieval_context`)**: 包含模块的详细定义，通过 `template_json` 获取每个模块的标准 JSON 结构。

### 输出 (Output)
*   **JSON 配置文件 (`generated_code`)**: 最终生成的 JSON 字符串，包含所有配置好的节点、坐标、参数和连线关系，可直接导入目标平台。

---

## 3. 主要参数

| 参数名 | 类型 | 说明 |
| :--- | :--- | :--- |
| `plan_ir` | `Dict` | 上游 Planning Agent 生成的规划图。 |
| `retrieval_context` | `Dict` | 包含 `relevant_nodes`，用于查找模块模板。 |

---

## 4. 关键函数详解

### 4.1 `CodingAgent.generate_json(self, plan_ir, retrieval_context)`
*   **作用**: 整个编码过程的主控函数。
*   **流程**:
    1.  **索引构建**: 建立 `module_type -> template` 的映射。
    2.  **ID 实例化**: 为每个逻辑 ID (`logic_id`) 生成真实的 UUID (`real_id`)。
    3.  **自动布局**: 调用 `topological_layout` 计算所有节点的 (x, y) 坐标。
    4.  **连线索引**: 调用 `build_reverse_connections` 预处理连线关系。
    5.  **节点生成**: 遍历节点列表，调用 `fill_template` 生成最终节点配置。
    6.  **序列化**: 将结果导出为 JSON 字符串。

### 4.2 `coding_utils.topological_layout(nodes, connections)`
*   **作用**: 实现自动化图形布局算法。
*   **逻辑**:
    1.  构建图的邻接表。
    2.  使用 Khan 算法或 BFS 进行**拓扑排序**，确定每个节点的层级 (Level)。
    3.  根据层级分配 **X 坐标**（深度），根据层内顺序分配 **Y 坐标**（同级排列）。
*   **输出**: 坐标字典 `{logic_id: {'x': 100, 'y': 200}}`。

### 4.3 `coding_utils.build_reverse_connections(connections, id_map)`
*   **作用**: 将“源->目标”的连接转换为平台需要的“目标->[来源]”格式。
*   **逻辑**: 遍历连接列表，构建以目标节点 ID 为 key 的反向查找表。
*   **输出**: 嵌套索引结构 `target_logic_id -> input_port -> source_info`。

### 4.4 `coding_utils.fill_template(template, node, ...)`
*   **作用**: 将抽象数据注入到具体的 JSON 模板中。
*   **逻辑**:
    1.  深拷贝原始模板。
    2.  注入基础属性：`id`, `z` (Tab ID), `x`, `y`, `wires`。
    3.  注入业务参数：将 `parameters` 中的键值对覆盖到模板中（如处理 `inputCount` -> `inputs` 映射）。
    4.  处理名称：如果未指定 `name`，使用 `reasoning` 或类型作为默认名。
    5.  **清理**: 递归删除模板中未被替换的 `{{placeholder}}` 字段，保持配置纯净。

### 4.5 `coding_utils.generate_short_uuid()`
*   **作用**: 生成类似 `b45d2af` 的 7 位短 UUID，用于节点 ID。

---

## 5. 工作流程总结

1.  **资源准备**: 接收规划图（Plan）和模块定义（Schema）。
2.  **实例化**: 将抽象的 `logic_id` 转换为系统可用的真实 UUID。
3.  **空间计算**: 运行图算法，计算模块在画布上的最佳位置，避免重叠。
4.  **连接转换**: 将逻辑连线转换为底层 `wires` 数组格式（Node-RED 风格）。
5.  **参数落地**: 结合 Template + Parameters，生成完整的节点配置。
6.  **打包**: 添加容器页（Tab Node），输出最终 JSON。
