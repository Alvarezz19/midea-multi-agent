# 编码智能体 (Coding Agent) 工作流总结

## 1. 智能体结构与职责

**Coding Agent** 是系统中的"执行工匠"，负责将抽象的逻辑规划（逻辑ID、拓扑图）落地为详细的、平台可执行的 JSON 配置文件。它不涉及 LLM 推理，而是使用确定性算法进行数据映射和模板填充。

### 核心组成
*   **CodingAgent 类**: 核心协调器，串联整个编码流程。
*   **辅助工具集 (`coding_utils`)**: 包含 `resolve_input_count`（输入端口解析）、`topological_layout`（自动布局）、`build_reverse_connections`（连线转换）、`fill_template`（参数注入）等独立函数。

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
    1.  **索引构建**: 建立 `module_type -> template` 的映射（同时保留完整 `module_doc` 用于兜底端口计算）。
    2.  **ID 实例化**: 为每个逻辑 ID (`logic_id`) 生成真实的 UUID (`real_id`)。
    3.  **自动布局**: 调用 `topological_layout` 计算所有节点的 (x, y) 坐标。
    4.  **连线索引**: 调用 `build_reverse_connections` 预处理连线关系。
    5.  **输入端口解析**: 调用 `resolve_input_count` 通用地确定每个节点的输入端口数量。
    6.  **节点生成**: 遍历节点列表，构建 `wires` 数组，调用 `fill_template` 生成最终节点配置。
    7.  **序列化**: 将结果导出为 JSON 字符串。

### 4.2 `coding_utils.resolve_input_count(template_inputs, planned_params, module_doc)`
*   **作用**: 通用地确定节点的输入端口数量，处理所有模板中 `inputs` 字段的命名模式。
*   **背景**: 不同模块的 schema 使用了不同的参数名来控制输入端口数量，模板中 `inputs` 字段的占位符存在多种命名约定。
*   **支持的模式**:

    | 模式 | 模板占位符 | 解析方式 | 涉及模块 |
    | :--- | :--- | :--- | :--- |
    | A | `"{{inputs}}"` | `planned_params['inputs']` | 数学运算模块（加/减/乘/除/模/统计/位运算/冒泡排序） |
    | B | `"{{inputCount}}"` | `planned_params['inputCount']` | 变量模块（物理输出/变量/Modbus_IO/BACIP_IO） |
    | C | `"{{inputsCount}}"` | `planned_params['inputsCount']` | 控制/逻辑/定时/累计/应用模块（回差控制/比较判断/逻辑运算/限值/线性变换/PID 等） |
    | D | `"{{channelsPlusOne}}"` | `planned_params['channels'] + 1` | 通道选择模块（特殊计算） |
    | E | 固定数值 | 直接使用（规划参数可覆盖） | 无动态端口的模块（绝对值/触发开关/RS/SR 触发器等） |

*   **逻辑**:
    1.  解析模板 `inputs` 字段：如果是占位符字符串，通过 `_extract_placeholder_name()` 提取参数名。
    2.  **占位符匹配**: 使用提取的参数名到 `planned_params` 中查找对应值。
    3.  **特殊计算**: 对 `channelsPlusOne` 等派生参数执行计算（`channels + 1`）。
    4.  **别名回退**: 若精确匹配失败，依次尝试 `inputCount` → `inputsCount` → `inputs` 等常见别名。
    5.  **固定数值**: 若模板值为固定数字，直接使用（但允许规划参数覆盖）。
    6.  **兜底**: 所有策略失败时，从 `module_doc` 的 `ports_definition.inputs` 中统计 `condition == "always"` 的端口数量。
*   **输出**: `int` — 输入端口数量。

### 4.3 `coding_utils._extract_placeholder_name(value)`
*   **作用**: 从占位符字符串中提取参数名。
*   **示例**: `'{{inputsCount}}'` → `'inputsCount'`, `'{{channelsPlusOne}}'` → `'channelsPlusOne'`。
*   **输出**: 参数名字符串，非占位符时返回空字符串。

### 4.4 `coding_utils.topological_layout(nodes, connections)`
*   **作用**: 实现自动化图形布局算法。
*   **逻辑**:
    1.  构建图的邻接表。
    2.  使用 Khan 算法或 BFS 进行**拓扑排序**，确定每个节点的层级 (Level)。
    3.  根据层级分配 **X 坐标**（深度），根据层内顺序分配 **Y 坐标**（同级排列）。
*   **输出**: 坐标字典 `{logic_id: {'x': 100, 'y': 200}}`。

### 4.5 `coding_utils.build_reverse_connections(connections, id_map)`
*   **作用**: 将"源->目标"的连接转换为平台需要的"目标->[来源]"格式。
*   **逻辑**: 遍历连接列表，构建以目标节点 ID 为 key 的反向查找表。
*   **输出**: 嵌套索引结构 `target_logic_id -> input_port -> source_info`。

### 4.6 `coding_utils.fill_template(template, node, ...)`
*   **作用**: 将抽象数据注入到具体的 JSON 模板中。
*   **逻辑**:
    1.  深拷贝原始模板。
    2.  注入基础属性：`id`, `z` (Tab ID), `x`, `y`, `wires`。
    3.  **解析占位符映射**: 检查模板 `inputs` 字段是否为占位符（如 `"{{inputsCount}}"`），提取引用的参数名。
    4.  **注入业务参数**: 遍历 `parameters` 中的键值对覆盖到模板中，同时处理参数名到 `inputs` 的映射：
        - 若参数名与占位符引用的变量名匹配（如 `inputsCount`），同时写入 `result["inputs"]` 和 `result["inputsCount"]`。
        - 兼容旧逻辑：`inputCount` → `inputs`。
        - 特殊处理：`channelsPlusOne` 根据 `channels` 参数计算 `inputs = channels + 1`。
    5.  处理名称：如果未指定 `name`，使用模块原始名称作为默认名。
    6.  **清理**: 递归删除模板中未被替换的 `{{placeholder}}` 字段，保持配置纯净。

### 4.7 `coding_utils.generate_short_uuid()`
*   **作用**: 生成类似 `b45d2af` 的 7 位短 UUID，用于节点 ID。

### 4.8 `coding_utils.clean_placeholders(obj)`
*   **作用**: 递归清理 JSON 对象中包含 `{{}}` 占位符的字段。
*   **逻辑**: 遍历字典和列表，删除值仍为未替换占位符字符串的键，确保输出的 JSON 不含残留模板变量。

---

## 5. 工作流程总结

1.  **资源准备**: 接收规划图（Plan）和模块定义（Schema）。
2.  **实例化**: 将抽象的 `logic_id` 转换为系统可用的真实 UUID。
3.  **空间计算**: 运行图算法，计算模块在画布上的最佳位置，避免重叠。
4.  **输入端口解析**: 通过 `resolve_input_count` 通用解析模板占位符，确定每个节点的实际输入端口数量，确保 `wires` 数组长度正确。
5.  **连接转换**: 将逻辑连线转换为底层 `wires` 数组格式（Node-RED 风格）。
6.  **参数落地**: 结合 Template + Parameters，通过占位符映射将参数正确注入（包括 `inputs` 字段），生成完整的节点配置。
7.  **打包**: 添加容器页（Tab Node），输出最终 JSON。

---

## 6. 输入端口解析的设计背景

### 问题
不同类型的模块 schema 使用了不同的参数名来控制输入端口数量，模板中 `inputs` 字段的占位符命名不统一：

```
数学模块:      "inputs": "{{inputs}}"          ← 参数名 inputs
变量模块:      "inputs": "{{inputCount}}"      ← 参数名 inputCount
控制/逻辑模块: "inputs": "{{inputsCount}}"     ← 参数名 inputsCount
通道选择:      "inputs": "{{channelsPlusOne}}" ← 需要计算 channels + 1
固定端口模块:  "inputs": 2                     ← 直接是数值
```

### 解决方案
`resolve_input_count` 函数通过以下优先级链确定输入端口数量：

```
占位符精确匹配 → 特殊计算(channelsPlusOne) → 别名回退 → 固定数值 → ports_definition 兜底
```

该函数在 `CodingAgent.generate_json` 中被调用，同时传入 `module_doc`（包含 `ports_definition`）作为最终兜底依据。`fill_template` 中的参数注入也执行了对应的占位符映射逻辑，确保最终 JSON 中 `inputs` 字段被正确赋值，不会被 `clean_placeholders` 误删。
