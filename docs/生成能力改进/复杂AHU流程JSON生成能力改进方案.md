# 复杂 AHU 流程 JSON 生成能力改进方案

> 编写日期：2026-04-24  
> 适用范围：面向 `AHU程序/flows_*.json` 这类复杂 KONG CUBE / 图形流程序 JSON 的生成能力改进。  
> 依据：`复杂AHU流程JSON生成能力改进调研报告.md`、`工作流总结文档.md`、`工作流节点输入输出说明.md`、`workflow.py`、`agents/*.py`、`utils/*.py`、`schemas/*.json`、`AHU程序/flows_*.json`、`AHU程序/pattern_library/*.json`，并参考 LangGraph 官方 Graph / Interrupt / Persistence 文档。  

---

## 1. 目标和边界

本方案目标不是一次性生成完全等同真实项目的 900+ 对象 AHU 程序，而是把当前工作流从“能生成小型 Graph IR JSON”推进到“能生成可校验、可审计、逐步逼近真实 AHU 项目文件的复杂 JSON”。

目标产物形态参考 `AHU程序/flows_*.json`：

- 顶层是扁平对象数组。
- 包含 `tab`、`subflow`、`subflow:<id>` 实例和大量普通节点。
- 普通节点通过 `z` 挂载到页面或子流程定义。
- `wires` 表达端口级连接。
- 子流程定义不仅有接口壳，还必须有内部 body 节点。
- 真实样例对象数约 913 到 992，页签 4 到 6 个，子流程定义 5 到 6 个，子流程 body 节点约 256 到 295 个。

本轮边界：

- 暂时不改造 `RepairAgent`。
- 暂时不正式切换 `Send` 并行子系统派发。
- 不让 LLM 直接生成最终平台 JSON。
- 保留 `CodingAgent` 作为确定性编译器。
- 保留 `VerifierAgent` 作为结构和语义验收出口。
- 保留 `repair_router` 作为统一 route decision 和 API 诊断出口。

---

## 2. 当前状态判断

当前正式主链已经稳定：

```text
analysis
-> ambiguity_router
-> clarification_review / clarification_apply 或 retrieval
-> architecture_planning
-> architecture_review / architecture_feedback_apply
-> subsystem_planning
-> global_assembly
-> coding
-> verification
-> repair_router
-> END 或 repair_agent
```

关键状态链路已经成型：

```text
requirement_spec
-> retrieval_bundle
-> decomposition_result / architecture_plan
-> subsystem_plan_map
-> assembled_graph_ir
-> compiled_artifact
-> verification_report
-> final_output
```

当前 `AnalysisAgent` 已经使用 LLM，但后续 `RetrievalAgent`、`ArchitecturePlanner`、`SubsystemPlanner`、`GlobalAssembler`、`CodingAgent`、`VerifierAgent` 基本是规则、检索、模板和确定性编译驱动。

当前 `schemas/*.json` 已经保存了原子模块级知识，包括模块用途、参数 schema、端口定义和 `template_json`。因此，平台级节点合同不是从零建设，真正缺口是把这些 schema 从“检索资料 / 编译模板”升级为“可索引、可按需加载、可校验、可驱动 strict compile 的正式知识资产”。

`RepairAgent` 当前不是质量生成器，而是有限规则补丁器，主要处理：

- planning：共享信号 owner 重绑或 external 重分类。
- assembly：删除非法局部边。
- compile：修复 wire 端口越界。

因此，暂时绕过 `RepairAgent` 不会降低业务生成质量，但会降低结构错误的自动恢复能力。当前默认 `enable_repair_agent=False` 已经满足“不进入 RepairAgent”的运行方式；若 verifier 未通过，`repair_router` 会输出 `reject`，原因通常是 `repair_agent_disabled`。

---

## 3. 核心问题

### 3.1 子流程 body 未编译（第一轮已完成）

`AHU程序/pattern_library/subflow_templates.json` 已保留 `internal_flow_objects`。第一轮改进后，Graph IR 的 `SubflowDefinitionIR` 已携带 `internal_flow_objects`，`CodingAgent` 会展开内部 body 节点，并重映射 body `id`、`z`、`wires` 以及 subflow `in/out.wires`。

此前这会导致最终 JSON 有子流程壳和实例，但缺少子流程内部逻辑；当前最小闭环已覆盖“末端组空送风机标准控制”真实模板。

剩余缺口转为更高层的语义问题：跨页面 quote 引用补全、system pattern 标准对象组、golden diff 和 import-ready 评估。

### 3.2 `schemas/*.json` 尚未成为正式校验合同

当前 `schemas/*.json` 已包含大量节点合同雏形，例如 `schemas/variable/变量.json` 中的 `swInput` 已记录用法、参数类型、取值范围、端口定义和模板 JSON。问题不是没有原子模块知识，而是这些知识在正式主链中的消费仍不充分。

当前 verifier 已覆盖 JSON parse、顶层 list、`z` 父对象存在、`wires` 目标存在、端口范围等基础结构，但还没有系统性使用 `schemas/*.json` 做完整平台级 schema 和语义校验：

- `tab`、`subflow`、subflow instance 字段约束。
- 普通模块参数 schema 与默认值归一化。
- `quote.labelName` 引用语义。
- 子流程 definition/body 完整性。
- `subflow:<id>` 与真实定义对应关系。
- 动态端口和必需端口规则。
- compile warning 是否应升级为 hard fail。

因此，阶段目标应从“新增一套孤立平台 schema”调整为“以 `schemas/*.json` 为原子模块事实源，补充 flow 级结构 schema，并让 Verifier / CodingAgent / Planner 可按需消费这些合同”。

### 3.3 system pattern 仍偏摘要，不是装配蓝图

当前 `system_patterns.json` 能表达必有页、可选页和来源样例，但 `subsystem_slots`、`naming_hints`、`layout_hints`、`style_guides` 基本为空。

真实 AHU 程序存在稳定工程骨架：

- 标准页：`IO/通讯`、`控制`、`定时`、`直膨机状态`。
- 可选页：`排风机`、`直膨机故障`。
- 控制页放主要子流程实例。
- IO/通讯页承载大量点位和通讯映射。
- 定时页和直膨机状态页高度标准化。

### 3.4 复杂需求到 `requirement_spec` 的语义承接不足

复杂 AHU 输入需要包含点表、设备数量、通讯地址、模式、联锁、命名规则等。当前自然语言短句可以跑通，但对完整工程输入包支持不足。

风险是：后续规则链会“正确执行错误假设”。

### 3.5 模板选择和接口绑定过度依赖规则打分

`ArchitecturePlanner` 和 `SubsystemPlanner` 已有模板匹配、端口覆盖和降级逻辑，但复杂 AHU 的模板选择、端口语义、信号别名和共享信号归属仍需要语义判断。

如果模板接口不匹配，系统会降级到 `atomic_assembly`，输出质量和可维护性会下降。

### 3.6 知识资产缺少分层索引和按需加载机制

当前知识资产的事实源已经比较清楚：

- 原子模块事实源：`schemas/*.json`。
- AHU 样例事实源：`AHU程序/flows_*.json`。
- AHU 可重建缓存：`AHU程序/pattern_library/*.json`。
- 运行时检索缓存：Chroma collections。

但当前缺少类似 skills 的“渐进式披露、按需加载”组织方式。多数节点要么只拿向量检索摘要，要么拿完整 payload，缺少稳定的知识分层：

- L0：资产 registry / manifest，说明有哪些模块、模板、pattern、版本和来源。
- L1：轻量摘要卡片，用于检索、排序、规划。
- L2：结构化合同，用于接口绑定、模板填充、strict compile、verifier。
- L3：原始样例切片和 body，用于复杂编译、debug、golden diff。

没有这层结构，后续继续扩知识库会带来两个风险：检索上下文过重，以及知识更新后各节点消费口径不一致。

---

## 4. 总体技术路线

推荐顺序：

```text
保持 RepairAgent 默认关闭
-> 建立知识资产分层 registry 和按需加载口径
-> 将 schemas/*.json 升级为可消费的平台节点合同
-> 补 flow 级平台 JSON 合同和 strict compile
-> 实现 internal_flow_objects body 编译
-> 强化子流程接口语义和 system pattern 蓝图
-> 补强需求语义和 LLM 规划辅助
-> 增加平台语义 verifier 与 golden diff 回归
-> 再评估 RepairAgent 扩面和 Send 并行
```

LLM 的使用原则：

- LLM 负责语义增强、候选排序、接口适配建议、共享信号判别。
- LLM 应优先消费 L0/L1/L2 知识卡片和合同，不直接读取大量 raw flow。
- LLM 输出必须是结构化 JSON patch / advisory，不直接写最终 flow JSON。
- LLM 输出必须经过规则归一化和 verifier 验收。
- LLM 不可用时应降级到当前 deterministic 路径。

---

## 5. 改进阶段

### 阶段 0A：知识资产分层与 registry 设计

目标：先明确知识库的组织和消费边界，让后续补充知识时不会把所有 raw JSON 都塞进检索上下文，也不会让各节点各自解释同一份资产。

基本原则：

- `schemas/*.json` 是原子模块事实源，不应被可重建索引替代。
- `AHU程序/flows_*.json` 是 AHU 真实样例事实源。
- `AHU程序/pattern_library/*.json`、Chroma collections、后续 `knowledge_index` 都是可重建缓存。
- 节点按需加载知识，不把完整模板、完整 flow、完整 body 全量注入每个阶段。

建议采用四层知识披露模型：

| 层级 | 内容 | 主要消费者 |
| --- | --- | --- |
| L0 registry / manifest | `asset_id`、类型、来源、版本、hash、更新时间、payload locator | 健康检查、构建脚本、Retrieval metadata |
| L1 摘要卡片 | 模块名、角色、关键词、用途、端口摘要、来源摘要 | Retrieval、ArchitecturePlanner、LLM rerank |
| L2 结构化合同 | `parameters_schema`、`ports_definition`、`template_json`、接口约束、动态端口规则 | SubsystemPlanner、GlobalAssembler、CodingAgent、VerifierAgent |
| L3 原始样例 / body | `internal_flow_objects`、source flow slice、raw flow 引用 | CodingAgent body 展开、golden diff、debug |

建议新增或扩展：

- `utils/knowledge_asset_registry.py`
- `utils/knowledge_contract_loader.py`
- `scripts/build_knowledge_indexes.py`，或扩展现有 `scripts/build_phase2_retrieval_indexes.py`
- 可重建输出目录：`outputs/knowledge_index` 或继续放在 `AHU程序/pattern_library` 下分文件管理

实施步骤：

1. 从 `schemas/*.json` 生成 `atomic_module_cards` 和 `module_contract_index`。
2. 从 `subflow_templates.json` 生成 `subflow_template_cards`、`subflow_interface_contracts` 和 body locator。
3. 从 `system_patterns.json` 生成 `system_pattern_cards` 和 pattern contract。
4. Chroma 中优先写入 L1 摘要卡片；完整 L2/L3 payload 通过 locator 按需加载。
5. 在 `retrieval_bundle.metadata` 中记录命中的 asset id、asset level、source hash，便于 trace 和复现。

完成标准：

- 原子模块、子流程模板、system pattern 都有稳定 `asset_id` 和来源 hash。
- `RetrievalAgent` 可只检索 L1 卡片，下游可按 id 加载 L2/L3。
- 修改 `schemas/*.json` 或 `flows_*.json` 后能重建索引，并能通过 manifest 看出版本变化。
- 不需要手工 patch Chroma 或缓存文件作为事实源。

验收命令：

```powershell
conda activate midea
python scripts/build_phase2_retrieval_indexes.py --output-dir AHU程序/pattern_library
python -m unittest discover -s tests -p "test_phase2*.py"
```

---

### 阶段 0：运行策略收口

目标：明确短期主链不经过 `RepairAgent`，但保留 `repair_router`。

实施步骤：

1. 保持 `enable_repair_agent=False` 作为默认运行方式。
2. 文档和 API 说明中明确：默认不进入 `RepairAgent`，失败由 `repair_router` 归一化为 `reject`。
3. 不把 `verification` 直接接到 `END`，避免丢失 `route_decision`、reject reason 和 API diagnostics。
4. trace 中明确展示 `repair_agent_disabled`、`repair_scope`、`issue_ids`。

完成标准：

- Python 入口、API 入口均默认不进入 `repair_agent`。
- `verification_report.status=passed` 时仍能 `accept`。
- `verification_report.status!=passed` 且 `enable_repair_agent=False` 时，`route_decision.decision=reject`。
- API result / trace 能看到 reject 原因。

验收命令：

```powershell
conda activate midea
python -m unittest tests.test_phase4_workflow_repair_loop
python -m unittest tests.test_workflow_api
```

---

### 阶段 1：LLM 需求增强层

目标：把用户输入从短自然语言扩展为结构化 AHU 工程需求，减少后续规划误判。

建议新增或改造：

- 新增 `agents/requirement_enrichment_agent.py`，或在 `AnalysisAgent` 后增加 `requirement_enrichment` 节点。
- 新增 `utils/ahu_requirement_schema.py`，定义工程输入包 schema。
- 扩展 `requirement_spec`，但不破坏现有字段。

建议结构：

```json
{
  "project": {},
  "ahu_units": [],
  "points": [],
  "subsystems": [],
  "modes": [],
  "interlocks": [],
  "communication": {},
  "naming_convention": {},
  "acceptance_criteria": []
}
```

LLM 输入：

- `user_query`
- `analysis_result.scenario_analysis`
- 当前 `requirement_spec`
- L0/L1 知识卡片中的领域槽位说明，避免直接注入完整 raw flow 或完整模板 body

LLM 输出：

- `requirement_patch`
- `missing_required_fields`
- `confidence`
- `clarification_suggestions`
- `assumptions`

规则归一化要求：

- 只允许回写需求侧字段。
- 不允许直接生成 `architecture_plan`、`subsystem_plan_map`、`assembled_graph_ir`。
- 缺少点表、设备数量、通讯地址等关键字段时，触发 `clarification_review` 或写入高优先级 ambiguity。

完成标准：

- 对“生成完整 AHU 标准程序”类请求，能识别缺失点表、设备数量和通讯参数。
- `requirement_spec.subsystems`、`required_pages`、`global_modes`、`signals` 更完整。
- LLM 失败时仍能回退到当前 `AnalysisAgent + build_requirement_spec` 路径。

验收标准：

- 新增单测覆盖自然语言输入、工程输入包输入、LLM fallback。
- 对现有 Phase 6 query suite 不产生字段兼容回归。
- trace 中能看到 enrichment 是否启用、是否 fallback、补了哪些字段。

---

### 阶段 2：LLM 模板选择和接口适配辅助

目标：提升模板复用率，减少复杂 AHU 场景退化到 `atomic_assembly`。

建议新增能力：

1. 在 `ArchitecturePlanner` 中增加可选 LLM template rerank。
2. 在 `SubsystemPlanner` 中增加可选 LLM interface adapter。
3. 输出只作为候选建议，最终仍由规则校验决定是否采用。

LLM template rerank 输入：

- 子系统描述。
- 候选 `subflow_templates` 的 L1 摘要卡片。
- 候选模板端口、角色、内部节点数量、来源样例摘要。
- `system_pattern` 的 L1 摘要和必要 L2 合同。

输出：

```json
{
  "ranked_template_ids": [],
  "selection_reason": "",
  "required_bindings": [],
  "risk_flags": []
}
```

LLM interface adapter 输入：

- 选中模板 L2 接口合同和端口列表。
- 子系统 imports / exports。
- requirement signals。
- shared signal registry。

输出：

```json
{
  "port_binding_patch": [],
  "signal_aliases": {},
  "missing_bindings": [],
  "fallback_required": false,
  "reasoning": ""
}
```

完成标准：

- 复用模板时，端口绑定更贴近模板语义。
- 无法安全适配时仍明确降级，并记录 `degrade_reason`。
- LLM 建议不能绕过端口数量、必需绑定和 shared signal 校验。

验收标准：

- 新增送风机、排风机、冷水阀、电加热、CO2 风阀、直膨除湿的模板选择回归。
- 对模板接口明显不匹配的样例，仍必须降级或触发澄清。
- 生成 `subsystem_plan_map[*].template_binding` 中记录 LLM 建议和最终采用结果。

---

### 阶段 3：基于 `schemas` 的平台级合同消费与 strict compile

目标：先让最终 JSON 有硬合同，再扩展生成能力。这里不是重建一套独立的原子模块 schema，而是以 `schemas/*.json` 为模块事实源，补足 flow 级结构 schema，并让编译器和 verifier 能正式消费这些合同。

建议新增：

- `schemas/flow/flow_document.schema.json`
- `schemas/flow/tab.schema.json`
- `schemas/flow/subflow.schema.json`
- `schemas/flow/wire.schema.json`
- `utils/module_contract_loader.py`
- `utils/platform_flow_schema.py`
- `tests/test_platform_flow_schema.py`

校验范围：

- 顶层必须是 list。
- 每个对象必须是 dict 且有唯一 `id`。
- `tab` 必须有 `id/type/label/disabled/info`。
- `subflow` 必须有 `id/type/name/in/out`。
- `subflow:<id>` 必须引用真实 `subflow` 定义。
- 普通节点必须有合法 `z/x/y/wires`。
- `wires` target 必须引用真实对象。
- `quote.labelName` 必须能解析到合法引用，或明确作为待支持项失败。
- 普通节点的参数、默认值、端口数优先依据 `schemas/<category>/*.json` 中的 `parameters_schema`、`ports_definition` 和 `template_json`。
- 动态端口规则先覆盖高频模块，再逐步扩展，不能为了通过校验放宽为任意字段。

`schemas/*.json` 的正式消费口径：

- `parameters_schema`：用于参数类型、枚举、默认值、范围校验。
- `ports_definition`：用于端口数量、端口语义、动态端口启用条件校验。
- `template_json`：用于编译填充和占位符检测。
- `description / keywords / usage_guides`：用于 L1 摘要卡片和检索，不作为 hard validation 的唯一依据。

strict compile 要求：

- 缺模板、缺 scope、占位符残留、节点跳过、body 展开失败，默认 hard fail。
- `compile_report` 增加：
  - `dropped_node_count`
  - `missing_template_count`
  - `unresolved_placeholder_count`
  - `body_node_count`
  - `body_expansion_errors`
- `VerifierAgent` 对上述错误字段升级为 error。

完成标准：

- 三个真实 `AHU程序/flows_*.json` 作为正样本通过基础平台 schema 校验。
- 高频原子模块合同可从 `schemas/*.json` 加载，不再在 verifier 中手写散落规则。
- 故意破坏 `z`、`wires`、`subflow:<id>`、重复 id 时能稳定失败。
- 故意传入非法枚举、非法端口数、残留占位符时能稳定失败。
- 当前生成结果中任何跳过节点、占位符残留都不能被判为 passed。

验收命令：

```powershell
conda activate midea
python -m unittest tests.test_platform_flow_schema
python -m unittest tests.test_phase3_verifier_native_contract
```

---

### 阶段 4：`internal_flow_objects` body 编译

目标：让最终 JSON 具备完整子流程内部 body，不再只生成子流程壳。

建议修改：

- `utils/graph_ir.py`
  - `SubflowDefinitionIR` 增加 `internal_flow_objects` 或 `body_objects`。
- `agents/assembly_shared.py`
  - `_build_subflow_definition()` 从 `module_doc.internal_flow_objects` 携带 body。
- `agents/coding_agent.py`
  - 编译 `subflow` 定义时同步展开 body。
  - 对 body 节点做稳定 ID 重映射。
  - 重写 body 节点 `z` 为真实 subflow id。
  - 重写 body 内部 `wires` 目标 id。
  - 重写 `subflow.in/out.wires` 中指向内部节点的 id。
- `agents/verifier_agent.py`
  - 增加 `subflow.body.must_exist`、`subflow.inout.wires.must_target_body` 等校验。

关键规则：

- 同一个模板定义只展开一次 body。
- 多个子流程实例只生成多个 `subflow:<id>` 实例，不重复 body。
- body 内部原始 id 不泄露为最终 id。
- body 节点的 `z` 必须指向真实 subflow id。

完成标准：

- 使用送风机标准控制模板时，最终 JSON 包含：
  - 1 个 `tab`
  - 1 个 `subflow`
  - 该 subflow 的完整 body 节点，数量接近源模板 41 个
  - 1 个 `subflow:<id>` 实例
  - body 内部 wires 全部引用有效目标
  - subflow `in/out.wires` 引用有效 body 节点
- `compile_report.body_node_count > 0`。
- 删除 body 或破坏 body wires 时 verifier 必须失败。

验收命令：

```powershell
conda activate midea
python -m unittest tests.test_coding_subflow_body_expansion
python -m unittest tests.test_phase3_workflow
```

---

### 阶段 5：子流程接口语义和 system pattern 蓝图

目标：让资产层不只是检索结果，而是可以指导工程级装配。

本阶段新增知识应写回 L1/L2 合同层，而不是直接手改 Chroma。`subflow_templates.json` 和 `system_patterns.json` 仍可作为可重建缓存，但应通过构建脚本从事实源和标注规则重建。

子流程接口语义建议补充字段：

- `interface_schema`
- `required_bindings`
- `default_signal_aliases`
- `port_semantic_role`
- `port_value_type`

抽取来源：

- `ports_definition`
- `internal_flow_objects`
- 原子模块端口定义
- `subflow设计.json` 中的节点、边和描述
- 真实 `flows_*.json` 中的使用方式

system pattern 建议补充字段：

- `page_templates`
- `subsystem_slots`
- `standard_object_groups`
- `naming_hints`
- `layout_hints`
- `style_guides`

完成标准：

- 每个 AHU 子流程模板的输入输出端口有语义角色和类型。
- `ArchitecturePlanner` 能从 system pattern 生成标准页签和子系统槽位。
- `GlobalAssembler` 能根据 pattern 生成固定对象组，或至少生成明确 unresolved item。
- “完整 AHU 标准程序”不再只生成控制页和少量子系统，而是至少生成标准 4 页骨架。

验收标准：

- pattern library 构建测试覆盖接口语义和 page template。
- 真实三份 `flows_*.json` 的 pattern 抽取结果稳定。
- 对缺失标准页、缺失标准对象组的生成结果能给出结构化 issue。

---

### 阶段 6：语义 verifier 与 golden diff 回归

目标：从“结构能 parse”升级到“结构和业务语义可评估”。

建议新增：

- `utils/flow_canonicalizer.py`
- `utils/flow_golden_diff.py`
- `tests/test_flow_golden_diff_suite.py`
- `scripts/run_flow_golden_diff_suite.py`

verifier 分层：

1. `ir_verifier`：现有 Graph IR 校验。
2. `platform_schema_verifier`：完整 flow JSON schema。
3. `semantic_verifier`：端口类型、引用、模块参数、子流程 body。
4. `golden_diff_verifier`：与真实样例做规范化结构对比。

golden diff 规范化：

- 稳定化 ID。
- 去除或分桶坐标。
- 将 `wires` 转为结构边。
- 统计页签、子流程、节点类型、body 拓扑。
- 统计标准对象组覆盖率。
- 计算 canonical hash。

完成标准：

- 三个真实 `AHU程序/flows_*.json` 作为正样本通过 canonicalizer。
- 对生成结果输出：
  - `structural_pass`
  - `semantic_pass`
  - `layout_pass`
  - `import_ready`
- 对完整 AHU 目标和局部子系统目标采用不同阈值，不把局部生成误判为完整失败。

验收命令：

```powershell
conda activate midea
python scripts/run_flow_golden_diff_suite.py
python -m unittest tests.test_flow_golden_diff_suite
```

---

### 阶段 7：再评估 RepairAgent 扩面和 Send 并行

目标：等质量合同稳定后，再决定是否扩大自动修复和并行化。

RepairAgent 扩面前提：

- 新 verifier 能稳定产出高频失败桶。
- 每个失败桶有明确 patch 计划和回归测试。
- 高风险 patch 需要进入 `repair_review`，不能静默改 IO/通讯/地址/点位。

可考虑的 repair 类型：

- `missing_subflow_body`
- `unresolved_placeholder`
- `invalid_quote_reference`
- `template_port_binding_mismatch`
- `missing_standard_page_group`
- `dropped_node_detected`

Send 并行前提：

- `subsystem_plan_map` reducer 明确。
- 并行结果与串行结果 canonical 等价。
- trace 顺序稳定。
- 共享信号冲突可解释且可 fail-fast。

完成标准：

- 有真实失败桶数据支持扩面，而不是预设 repair。
- 并行 POC 与正式串行主链输出规范化等价。
- 不因并行引入不可解释的状态覆盖。

---

## 6. 推荐执行顺序

短期执行顺序：

1. 阶段 0A：知识资产分层与 registry 设计。
2. 阶段 0：运行策略收口。
3. 阶段 3：基于 `schemas` 的平台级合同消费与 strict compile。
4. 阶段 4：`internal_flow_objects` body 编译。
5. 阶段 5：子流程接口语义和 system pattern 蓝图。
6. 阶段 1：LLM 需求增强层。
7. 阶段 2：LLM 模板选择和接口适配辅助。
8. 阶段 6：语义 verifier 与 golden diff 回归。
9. 阶段 7：RepairAgent 扩面和 Send 并行评估。

理由：

- 知识资产分层是轻量前置，不是大规模补知识；它解决后续知识如何被检索、按需加载和重建。
- `schemas/*.json` 已经有原子模块合同，应先被 verifier / compiler 正式消费，而不是另建一套孤立规则。
- body 编译和平台 schema 是硬合同，优先级高于 LLM 质量增强。
- LLM 应消费结构化知识卡片和合同，服务于需求增强、模板排序和接口适配，而不是直接写平台 JSON。
- RepairAgent 和 Send 都是后续放大器，不能早于质量合同。

---

## 7. 最小闭环验收

第一轮不追求完整 900+ 对象程序，先做最小可验证闭环。

输入目标：

```text
生成一个包含末端组空送风机标准控制子流程的 AHU 控制程序。
```

最终 JSON 必须包含：

- 1 个 `tab`。
- 1 个 `subflow` 定义。
- 该 subflow 的完整 body 节点，数量接近源模板 41 个。
- 1 个 `subflow:<id>` 实例。
- body 节点 `z` 指向真实 subflow id。
- body 内部 wires 全部引用有效目标。
- subflow `in/out.wires` 引用有效 body 节点。
- `verification_report.status=passed`。
- `route_decision.decision=accept`。

负样本必须失败：

- 删除 body 节点。
- 破坏 body 内部 wire target。
- 删除 subflow 定义。
- 让 `subflow:<id>` 指向不存在定义。
- 留下 `{{placeholder}}`。
- 编译器跳过节点。

---

## 8. 总结

当前工作流的主干方向正确，真正短板不是缺一个更大的 agent，而是缺更硬的产物合同和更强的语义投影。

本方案的关键判断是：

- `schemas/*.json` 已经是原子模块合同事实源，下一步要把它升级为可检索、可按需加载、可校验、可编译约束的正式知识资产。
- 知识库扩展不应作为一个长期大前置，而应按 L0/L1/L2/L3 分层，随各阶段验收一起增量推进。
- `RepairAgent` 暂时不作为质量提升主路径。
- `repair_router` 应保留为统一诊断出口。
- `CodingAgent` 应继续保持确定性编译器角色。
- LLM 应放在需求增强、模板排序、接口适配和共享信号判别位置，并优先消费结构化知识卡片和合同。
- 基于 `schemas` 的平台合同消费、body 编译、语义 verifier、golden diff 是复杂 AHU JSON 能力升级的主线。
