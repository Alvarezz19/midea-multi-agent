# LLM 节点增强落地方案

> 编写日期：2026-04-26  
> 适用范围：在当前正式工作流中，为 `analysis`、`retrieval`、`architecture_planning`、`subsystem_planning`、`verification` 等节点引入可控 LLM 能力，以提升 `AHU程序/flows_*.json` 形态产物质量。  
> 前置依据：`工作流总结文档.md`、`工作流节点输入输出说明.md`、`docs/生成能力改进/复杂AHU流程JSON生成能力改进方案.md`、`docs/生成能力改进/下一步开工计划.md`、`workflow.py`、`agents/*.py`、`utils/*.py`、`schemas/*.json`、`AHU程序/flows_*.json`。  
> LangGraph 依据：官方 Graph API、Interrupt、Persistence、Durable Execution 文档。Graph 由节点和边组成；`interrupt()` 依赖 checkpointer 和 `thread_id` 恢复；durable execution 要求非确定性和副作用操作保持确定性、幂等，或封装在可恢复 task 中。  
> 官方文档链接：  
> - https://docs.langchain.com/oss/python/langgraph/graph-api  
> - https://docs.langchain.com/oss/python/langgraph/interrupts  
> - https://docs.langchain.com/oss/python/langgraph/persistence  
> - https://docs.langchain.com/oss/python/langgraph/durable-execution

---

## 1. 结论先行

当前工作流只有 `AnalysisAgent` 直接调用 LLM。对于复杂 AHU 目标产物，这确实不够，但不应该把所有节点都改成 LLM Agent。

推荐原则：

- LLM 负责语义判断、候选排序、接口适配、业务完整性复核。
- 规则代码负责状态归一化、资产白名单、装配、编译、ID / `z` / `wires`、平台 schema 校验。
- `CodingAgent`、`GlobalAssembler` 主路径、`RepairRouter` 继续保持确定性。
- LLM 输出必须是结构化 advisory 或 patch，不直接输出最终 `flows JSON`。
- LLM 不可用、超时或输出不合法时，必须回退到当前 deterministic 路径。

建议优先级：

| 优先级 | 节点 | 新能力 | 判断 |
| --- | --- | --- | --- |
| P0 | `analysis` | LLM 工程需求编译与澄清信号增强 | 从自然语言提取 AHU 工程结构、点位、回路、联锁和缺失项 |
| P0 | `retrieval` | LLM 查询改写 + Cross-Encoder reranker 重排 | LLM 负责改写查询，专用 reranker 负责候选排序 |
| P0 | `subsystem_planning` | LLM 子系统接口适配 | 直接提升 `template_binding`、端口绑定、局部 IR 质量 |
| P1 | `architecture_planning` | LLM 架构草案与模板候选排序 | 提升页签、子系统槽位、共享信号归属 |
| P1 | `verification` | LLM 语义复核 critic | 补足业务规则、工程完整性、风格一致性检查 |
| P2 | `global_assembly` | 仅在 unresolved 时 LLM 语义补洞 | 不接管装配，只给候选绑定 |
| P2 | `repair_agent` | LLM 修复建议 advisory | 不直接 apply patch，只生成候选修复说明 |

明确不做：

- 不让 LLM 直接生成 `compiled_artifact.json_text`。
- 不让 LLM 接管 `CodingAgent`。
- 不让 LLM 生成不存在的 `module_type`、`template_id`、`pattern_id`。
- 不在没有 verifier 的情况下采用 LLM patch。
- 不把 LLM 输出写入 `compiled_artifact`，LLM 只影响上游 IR 或诊断。

---

## 2. 当前基线

### 2.1 正式主链

当前主链：

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

关键状态链：

```text
user_query
-> analysis_result
-> requirement_spec
-> retrieval_bundle
-> decomposition_result / architecture_plan
-> subsystem_plan_map
-> assembled_graph_ir
-> compiled_artifact
-> verification_report
-> route_decision
-> final_output
```

当前直接 LLM 调用：

- `agents/analysis_agent.py`
  - `AnalysisAgent.__init__()` 初始化 `LLMManager.get_llm(...)`
  - `AnalysisAgent.analyze()` 使用 `with_structured_output(AnalysisResult)`
  - 失败后回退普通 `invoke()` 和本地 fallback

当前 `AnalysisAgent` 已调用 LLM，但输出仍偏轻量：

- `retrieval_plan` 主要服务检索。
- `scenario_analysis` 是业务摘要和少量槽位。
- `requirement_spec` 主要由 `utils.phase3_adapters.build_requirement_spec()` 从 `scenario_analysis` 规则推断。
- 对复杂 AHU 来说，子系统边界、控制回路、工程点位、通讯点、联锁、报警、默认假设和澄清项承接不足。

因此，`AnalysisAgent` 不应被视为已经完成，而应作为第一批增强对象，升级成“工程需求编译器”。

当前未使用 LLM 的关键节点：

- `RetrievalAgent` 构造参数保留 `llm_provider / llm_model`，但注释为当前未使用。
- `ArchitecturePlanner` 是规则和打分式系统骨架规划。
- `SubsystemPlanner` 是规则式模板复用和 atomic fallback。
- `GlobalAssembler` 是确定性全局 IR 装配。
- `CodingAgent` 是确定性 JSON 编译器。
- `VerifierAgent` 是规则优先结构和平台 schema 校验器。
- `RepairAgent` 是有限规则 patch 器。

### 2.2 目标产物特点

目标参考 `AHU程序/flows_*.json`：

- 顶层是扁平对象数组。
- 对象规模约 913 到 992。
- 页签 4 到 6 个。
- 子流程定义 5 到 6 个。
- 包含 `tab`、`subflow`、`subflow:<id>` 实例、普通节点、subflow body 节点。
- 普通节点通过 `z` 挂载到 tab 或 subflow。
- `wires` 是端口级连接。
- 质量不仅取决于 JSON 结构，还取决于模板选择、端口绑定、点位语义、共享信号、PID / 手自动 / 联锁 / 延时 / 报警完整性。

因此，LLM 增强应该发生在“理解和规划”阶段，而不是“编译和落盘”阶段。

---

## 3. 总体架构

### 3.1 新增 LLM 增强层

建议新增一个通用增强包：

```text
agents/llm_enhancers/
  __init__.py
  base.py
  retrieval_rewrite.py
  architecture_advisor.py
  subsystem_interface_adapter.py
  semantic_verifier.py
```

检索候选重排不放在 `llm_enhancers` 中，建议单独放到 reranker 工具层：

```text
utils/reranker_manager.py
utils/retrieval_rerank.py
```

也可以先不拆子目录，最小落地为：

```text
agents/retrieval_llm_enhancer.py
agents/architecture_llm_advisor.py
agents/subsystem_llm_adapter.py
agents/semantic_verifier_agent.py
```

推荐第一种，因为后续会有多个节点复用配置、结构化输出、fallback 和诊断字段。

### 3.2 通用设计

所有 LLM 增强器都遵循同一约束：

```text
输入：当前节点已有正式输入 + 检索资产 L1/L2 摘要 + 必要 trace 摘要
输出：结构化 advisory / patch
采用：由当前节点本地规则归一化、过滤、校验后再写回 WorkflowState
失败：记录 llm_enhancement.fallback_reason，回退 deterministic 路径
```

禁止：

```text
LLM -> compiled_artifact.json_text
LLM -> flow_objects
LLM -> raw file write
LLM -> 不存在资产 ID
LLM -> 绕过 VerifierAgent
```

### 3.3 状态字段策略

为了不破坏 `WorkflowState` 主契约，第一轮不建议新增多个顶层字段。优先将增强诊断写入既有对象的 `metadata` 或 `warnings`。

建议逐步引入一个顶层可选字段：

```python
llm_enhancement: dict
```

第一轮如果担心改动面，可以不加顶层字段，只写入：

- `retrieval_bundle.metadata.llm_rewrite`
- `retrieval_bundle.metadata.reranker`
- `architecture_plan.metadata.llm_advisor`
- `subsystem_plan_map[*].template_binding.llm_advisory`
- `verification_report.warnings`
- `verification_report.metrics.semantic_warning_count`，后续再加

如果新增顶层字段，建议结构：

```json
{
  "enabled_nodes": [],
  "node_results": {
    "retrieval": {},
    "architecture_planning": {},
    "subsystem_planning": {},
    "verification": {}
  },
  "fallbacks": [],
  "model_usage": []
}
```

第一轮不要求 API / 前端展示完整 `llm_enhancement`，只保证 trace 能看见。

---

## 4. 配置设计

### 4.1 总开关

在 `config.py` 增加：

```python
LLM_ENHANCEMENT_ENABLED = os.getenv("LLM_ENHANCEMENT_ENABLED", "false").lower() == "true"
LLM_ENHANCEMENT_PROVIDER = os.getenv("LLM_ENHANCEMENT_PROVIDER", "").strip()
LLM_ENHANCEMENT_MODEL = os.getenv("LLM_ENHANCEMENT_MODEL", "").strip()
LLM_ENHANCEMENT_TEMPERATURE = float(os.getenv("LLM_ENHANCEMENT_TEMPERATURE", "0.1"))
LLM_ENHANCEMENT_TIMEOUT_S = float(os.getenv("LLM_ENHANCEMENT_TIMEOUT_S", "20"))
```

### 4.2 分节点开关

```python
ANALYSIS_USE_ENGINEERING_COMPILER = os.getenv("ANALYSIS_USE_ENGINEERING_COMPILER", "false").lower() == "true"
ANALYSIS_ENGINEERING_LLM_PROVIDER = os.getenv("ANALYSIS_ENGINEERING_LLM_PROVIDER", "").strip()
ANALYSIS_ENGINEERING_LLM_MODEL = os.getenv("ANALYSIS_ENGINEERING_LLM_MODEL", "").strip()
ANALYSIS_ENGINEERING_LLM_TIMEOUT_S = float(os.getenv("ANALYSIS_ENGINEERING_LLM_TIMEOUT_S", "30"))

RETRIEVAL_USE_LLM_REWRITE = os.getenv("RETRIEVAL_USE_LLM_REWRITE", "false").lower() == "true"
RETRIEVAL_USE_CROSS_ENCODER_RERANK = os.getenv("RETRIEVAL_USE_CROSS_ENCODER_RERANK", "false").lower() == "true"
RETRIEVAL_RERANKER_PROVIDER = os.getenv("RETRIEVAL_RERANKER_PROVIDER", "bge").strip()
RETRIEVAL_RERANKER_MODEL = os.getenv("RETRIEVAL_RERANKER_MODEL", "BAAI/bge-reranker-v2-m3").strip()
RETRIEVAL_RERANK_TOP_N = int(os.getenv("RETRIEVAL_RERANK_TOP_N", "50"))
RETRIEVAL_RERANK_BATCH_SIZE = int(os.getenv("RETRIEVAL_RERANK_BATCH_SIZE", "16"))

ARCHITECTURE_USE_LLM_ADVISOR = os.getenv("ARCHITECTURE_USE_LLM_ADVISOR", "false").lower() == "true"
ARCHITECTURE_LLM_PROVIDER = os.getenv("ARCHITECTURE_LLM_PROVIDER", "").strip()
ARCHITECTURE_LLM_MODEL = os.getenv("ARCHITECTURE_LLM_MODEL", "").strip()
ARCHITECTURE_LLM_TIMEOUT_S = float(os.getenv("ARCHITECTURE_LLM_TIMEOUT_S", "20"))

SUBSYSTEM_USE_LLM_ADAPTER = os.getenv("SUBSYSTEM_USE_LLM_ADAPTER", "false").lower() == "true"
SUBSYSTEM_LLM_PROVIDER = os.getenv("SUBSYSTEM_LLM_PROVIDER", "").strip()
SUBSYSTEM_LLM_MODEL = os.getenv("SUBSYSTEM_LLM_MODEL", "").strip()
SUBSYSTEM_LLM_TIMEOUT_S = float(os.getenv("SUBSYSTEM_LLM_TIMEOUT_S", "30"))

VERIFICATION_USE_LLM_CRITIC = os.getenv("VERIFICATION_USE_LLM_CRITIC", "false").lower() == "true"
VERIFICATION_LLM_PROVIDER = os.getenv("VERIFICATION_LLM_PROVIDER", "").strip()
VERIFICATION_LLM_MODEL = os.getenv("VERIFICATION_LLM_MODEL", "").strip()
VERIFICATION_LLM_TIMEOUT_S = float(os.getenv("VERIFICATION_LLM_TIMEOUT_S", "30"))
```

### 4.3 默认策略

- 所有新开关默认 `false`。
- 单测默认使用 fake LLM，不访问真实网络。
- 本地试跑时可以只打开一个节点，避免一次性引入多处非确定性。
- 生产或长链路运行时必须配合 trace，记录模型、耗时、fallback、采用结果。

### 4.4 模型选择

复用现有 `utils/model_manager.py` 的 `LLMManager.get_llm(...)`。

节点内模型解析顺序：

```text
节点专用 provider/model
-> LLM_ENHANCEMENT_PROVIDER / LLM_ENHANCEMENT_MODEL
-> 全局 LLM_PROVIDER / 对应默认模型
```

温度建议：

| 节点 | 温度 |
| --- | --- |
| analysis engineering compiler | 0.1 到 0.2 |
| retrieval rewrite | 0.1 到 0.2 |
| architecture advisor | 0.1 到 0.2 |
| subsystem interface adapter | 0 到 0.1 |
| semantic verifier | 0 到 0.1 |

`retrieval` 的候选重排不使用通用 LLM，不需要 temperature。推荐使用专用 Cross-Encoder reranker，例如 `BAAI/bge-reranker-v2-m3`。BGE 和 Sentence Transformers 官方都采用“先 bi-encoder 召回，再 cross-encoder 重排”的两阶段检索架构。参考：

- https://bge-model.com/Introduction/reranker.html
- https://bge-model.com/tutorial/5_Reranking/5.1.html
- https://www.sbert.net/examples/applications/retrieve_rerank/README.html

`RETRIEVAL_USE_CROSS_ENCODER_RERANK` 是核心效果对比开关：

- `false`：保持当前向量检索 / 规则排序基线。
- `true`：对召回候选启用 Cross-Encoder reranker。

---

## 4A. 工作包 A0：AnalysisAgent 工程需求编译增强

### 4A.1 目标

把 `AnalysisAgent` 从“检索计划 + 场景摘要生成器”升级为“AHU 工程需求编译器”。

当前 `AnalysisAgent` 已经使用 LLM，但它主要输出：

- `retrieval_plan`
- `scenario_analysis`
- `metadata`

随后 `requirement_spec` 由 `build_requirement_spec(analysis_result)` 规则推断。这对简单需求够用，但复杂 AHU 需要更强的工程语义结构。

增强目标：

- 显式识别系统类型、设备对象、控制对象树。
- 显式识别子系统、控制回路、点位、联锁、报警、模式、通讯和页面需求。
- 区分“用户明确给出”和“模型保守假设”。
- 将缺失点表、设备数量、通讯地址、控制策略等问题转成 `ambiguities` 和 `clarification_signals`。
- 为 `retrieval` 提供更精确的 template / pattern 查询线索。
- 为 `architecture_planning` 提供更稳定的 `requirement_spec.subsystems / signals / required_pages / global_modes / acceptance_criteria`。

### 4A.2 修改文件

- `config.py`
- `agents/analysis_agent.py`
- `utils/phase3_adapters.py`
- 可选新增 `utils/ahu_requirement_schema.py`
- `tests/test_phase3_requirement_spec.py`
- 新增 `tests/test_analysis_engineering_compiler.py`

### 4A.3 推荐实现方式

不要推翻现有 `AnalysisResult`。建议在 `AnalysisAgent.analyze()` 中增加第二层结构化输出，或扩展现有结构化输出。

推荐第一轮采用“双阶段”：

```text
现有 AnalysisResult
-> build_requirement_spec 生成当前 requirement_spec
-> EngineeringRequirementCompiler 生成 requirement_patch
-> deterministic merge / normalize
-> derive_clarification_signals
```

理由：

- 保留当前 retrieval_plan 行为。
- 新能力失败时可完全回退。
- 便于单独测试工程需求补丁。
- 不需要一次性重写 `build_requirement_spec()`。

### 4A.4 新增结构化输出

建议新增 Pydantic 模型：

```python
class AhuPointSpec(BaseModel):
    name: str = ""
    point_role: str = ""  # sensor, actuator, setpoint, command, status, alarm, mode, parameter
    subsystem_id: str = ""
    io_kind: str = ""  # physical_input, physical_output, software_point, communication_point
    protocol: str = ""  # modbus, bacnet, mqtt, local, unknown
    address_hint: str = ""
    explicit: bool = False
    confidence: float = 0.0

class AhuControlLoopSpec(BaseModel):
    loop_id: str = ""
    subsystem_id: str = ""
    target: str = ""
    strategy: str = ""  # pid, hysteresis, on_off, sequence, interlock, schedule
    pv_signal: str = ""
    sp_signal: str = ""
    mv_signal: str = ""
    constraints: list[str] = Field(default_factory=list)
    explicit: bool = False
    confidence: float = 0.0

class AhuInterlockSpec(BaseModel):
    interlock_id: str = ""
    subsystem_id: str = ""
    condition: str = ""
    action: str = ""
    severity: str = ""  # stop, inhibit, alarm, limit, fallback
    explicit: bool = False
    confidence: float = 0.0

class AhuRequirementPatch(BaseModel):
    system_type: str = ""
    project_summary: str = ""
    subsystem_patches: list[dict] = Field(default_factory=list)
    required_pages: list[str] = Field(default_factory=list)
    global_modes: list[str] = Field(default_factory=list)
    points: list[AhuPointSpec] = Field(default_factory=list)
    control_loops: list[AhuControlLoopSpec] = Field(default_factory=list)
    interlocks: list[AhuInterlockSpec] = Field(default_factory=list)
    communication: dict[str, Any] = Field(default_factory=dict)
    naming_convention: dict[str, Any] = Field(default_factory=dict)
    acceptance_criteria: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    missing_required_fields: list[str] = Field(default_factory=list)
    confidence: float = 0.0
```

字段说明：

- `explicit=true` 表示用户原文明确给出。
- `explicit=false` 表示模型根据 AHU 常识做的保守推断。
- 精确地址、点位数量、设备数量不能凭空生成；用户未给出时写入 `missing_required_fields` 或 `ambiguities`。

### 4A.5 Prompt 要求

Prompt 必须强调：

- 不得编造用户未给出的通讯地址、设备数量、点位编号。
- 不得直接生成平台 JSON。
- 不得直接选择不存在的模板 ID。
- 能确定的写入结构化字段。
- 不能确定的写入 `ambiguities` 或 `missing_required_fields`。
- 每个点位和回路要标记 `explicit` 和 `confidence`。
- 输出只作为 `requirement_spec` 补丁，后续规划和校验会继续收口。

### 4A.6 合并规则

新增或扩展：

```python
def merge_engineering_requirement_patch(
    requirement_spec: dict,
    patch: dict,
) -> dict:
    ...
```

合并原则：

- 不覆盖用户明确字段，除非 patch 置信度更高且有 evidence。
- 只追加去重后的 `subsystems / signals / required_pages / global_modes / acceptance_criteria`。
- `points`、`control_loops`、`interlocks` 可先放在扩展字段：

```json
{
  "engineering": {
    "points": [],
    "control_loops": [],
    "interlocks": [],
    "communication": {},
    "naming_convention": {}
  }
}
```

- 不让下游必须立刻消费 `engineering` 扩展字段；先保证兼容现有正式字段。
- `missing_required_fields` 应转入 `requirement_spec.ambiguities` 或 `warnings`。

### 4A.7 澄清信号增强

当前 `derive_clarification_signals()` 主要看空字段、低置信度和 warnings。增强后应追加：

- 缺少设备数量：`missing_equipment_quantity`
- 缺少点表：`missing_point_schedule`
- 缺少通讯地址：`missing_communication_address`
- 缺少控制目标：`missing_control_target`
- 缺少 PID 反馈或设定值：`missing_pid_loop_signals`
- 模式冲突：`conflicting_global_modes`
- 模板复用风险：`insufficient_template_binding_evidence`

只有 high severity 才触发澄清 review。

### 4A.8 写回位置

`AnalysisAgent.__call__()` 最终写回：

```python
state["analysis_result"] = {
    ...,
    "engineering_analysis": {
        "enabled": True,
        "llm_used": True,
        "fallback_used": False,
        "patch_summary": {},
        "missing_required_fields": [],
        "confidence": 0.0
    },
    "clarification_signals": {}
}
state["requirement_spec"] = merged_requirement_spec
```

`requirement_spec` 建议追加：

```json
{
  "engineering": {
    "points": [],
    "control_loops": [],
    "interlocks": [],
    "communication": {},
    "naming_convention": {}
  }
}
```

### 4A.9 测试

新增测试：

- 简单数学需求：不应误识别为 AHU 工程需求。
- 复杂 AHU 需求：识别送风机、冷水阀、电加热、风阀、直膨等子系统。
- PID 需求：识别 PV / SP / MV、P/I/D、上下限、死区、计算间隔。
- 缺少点表和通讯地址：写入 `missing_required_fields` 和 clarification signals。
- 用户明确给出 Modbus 地址：保留为 explicit 点位，不被模型改写。
- fake LLM 抛异常：回退到当前 `build_requirement_spec()`。
- 开关关闭：当前 Analysis 行为不变。

### 4A.10 完成标准

- 开关关闭时所有现有 analysis / phase3 测试通过。
- 开关打开且 fake LLM 返回工程补丁时，`requirement_spec.engineering` 存在并结构合法。
- `requirement_spec.subsystems / required_pages / global_modes / signals` 比当前基线更完整。
- 缺失关键工程输入时能触发 clarification signals。
- `retrieval_bundle.metadata.analysis_summary` 不受破坏。

### 4A.11 验收命令

```powershell
conda activate midea
python -m unittest tests.test_analysis_engineering_compiler
python -m unittest tests.test_phase3_requirement_spec
python -m unittest tests.test_phase3_workflow
python -m unittest tests.test_phase8_clarification_contract
```

---

## 5. 工作包 A：Retrieval 查询改写和 Cross-Encoder 重排

### 5.1 目标

提升 `retrieval_bundle.subflow_templates` 和 `retrieval_bundle.system_patterns` 的命中质量，避免复杂 AHU 需求只召回原子模块，导致后续 `subsystem_planning` 退化到 `atomic_assembly`。

本工作包拆成两部分：

- LLM 只负责查询改写、术语归一、模板意图补全。
- Cross-Encoder reranker 负责候选重排。

不推荐用通用 LLM 做主重排。专用 reranker 对 query-candidate pair 直接打相关性分数，通常比让 LLM 输出候选 ID 排序更稳定、更便宜、更容易批处理和回归。

### 5.2 修改文件

- `config.py`
- `agents/retrieval_agent.py`
- 新增 `agents/llm_enhancers/retrieval_rewrite.py`
- 新增 `utils/reranker_manager.py`
- 新增 `utils/retrieval_rerank.py`
- `tests/test_phase2_retrieval_agent.py`
- 新增 `tests/test_retrieval_llm_enhancer.py`
- 新增 `tests/test_retrieval_cross_encoder_rerank.py`

### 5.3 查询改写输入

输入字段：

```json
{
  "user_query": "",
  "analysis_result": {
    "retrieval_plan": {},
    "scenario_analysis": {}
  },
  "requirement_hint": {
    "system_type": "",
    "subsystems": [],
    "required_pages": [],
    "global_modes": []
  },
  "asset_vocab": {
    "known_template_roles": [],
    "known_pattern_types": [],
    "known_module_types": []
  }
}
```

`asset_vocab` 第一轮可以从现有 `retrieval_bundle` 构建前的静态清单或 pattern library manifest 中读取，不要塞完整 raw flow。

### 5.4 查询改写输出

使用 Pydantic 结构化输出：

```python
class RetrievalRewriteResult(BaseModel):
    query_variants: list[str] = Field(default_factory=list)
    template_queries: list[str] = Field(default_factory=list)
    pattern_queries: list[str] = Field(default_factory=list)
    category_l1: str = ""
    normalized_terms: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
```

归一化规则：

- 每个列表去空、去重、限长。
- 不允许超过 `RETRIEVAL_LLM_MAX_QUERIES`。
- 不允许输出英文资产 ID 之外的虚构模板 ID。
- `risk_flags` 只进 metadata，不影响主链。

### 5.5 Cross-Encoder 重排输入

先执行当前向量检索，再把 top N 候选摘要送入 Cross-Encoder reranker。

输入：

```json
{
  "user_query": "",
  "requirement_summary": "",
  "candidate_subflow_templates": [
    {
      "template_id": "",
      "template_name": "",
      "template_role": "",
      "ports_summary": "",
      "source_flow": "",
      "similarity_score": 0.0
    }
  ],
  "candidate_system_patterns": [
    {
      "pattern_id": "",
      "system_type": "",
      "required_pages": [],
      "optional_pages": [],
      "similarity_score": 0.0
    }
  ]
}
```

候选摘要必须是短文本卡片，避免把完整 `internal_flow_objects` 或完整 raw flow 送入 reranker。

推荐候选文本：

```text
模板: {template_name}
角色: {template_role}
描述: {description}
端口: 输入 {input_port_names}; 输出 {output_port_names}
来源: {source_flow}
关键词: {keywords}
```

### 5.6 Cross-Encoder 重排输出

```python
class RerankedCandidate(BaseModel):
    asset_id: str
    asset_type: str
    vector_score: float = 0.0
    reranker_score: float = 0.0
    rule_score: float = 0.0
    final_score: float = 0.0

class RetrievalRerankResult(BaseModel):
    candidates: list[RerankedCandidate] = Field(default_factory=list)
    provider: str = ""
    model: str = ""
    fallback_used: bool = False
    fallback_reason: str = ""
```

采用规则：

- 只能重排向量检索已经召回的候选。
- reranker 不允许生成新 `template_id`、`pattern_id`、`module_type`。
- 如果 reranker 失败，保留向量排序或 RRF / rule score 排序。
- 最终排序可采用加权：

```text
final_score = reranker_score * 0.65 + vector_score * 0.25 + rule_score * 0.10
```

第一轮也可以更保守：

```text
final_score = reranker_score * 0.50 + vector_score * 0.50
```

`rule_score` 用于业务硬信号，例如：

- `template_role` 与 `subsystem_type` 精确匹配。
- 端口名覆盖 `requirement_spec.signals`。
- `system_type=AHU` 匹配。
- `selected_case_pattern_id` 匹配。

### 5.7 写回位置

写入：

- `retrieval_bundle.metadata.llm_rewrite`
- `retrieval_bundle.metadata.reranker`
- `retrieval_bundle.metadata.reranker_model`
- `retrieval_bundle.metadata.reranker_fallback_used`
- `retrieval_bundle.metadata.reranker_enabled`
- `retrieval_bundle.metadata.top_subflow_template_ids`
- `retrieval_bundle.metadata.top_system_pattern_ids`

不要改变 `retrieval_bundle` 的正式结构。

### 5.8 测试

新增测试：

- fake LLM 返回 AHU 查询扩展，断言 query variants 合并生效。
- fake reranker 返回固定分数，断言排序调整。
- fake reranker 返回异常，断言回退原排序。
- reranker 只能处理候选内 asset id，断言不会创造新资产。
- `RETRIEVAL_USE_CROSS_ENCODER_RERANK=false` 时不调用 reranker。
- fake LLM 抛异常，断言回退 deterministic 检索。
- 开关关闭时行为与当前基线一致。

### 5.9 完成标准

- 默认关闭时所有现有 Phase 2 测试通过。
- 打开 rewrite 后，metadata 能看到 LLM 查询。
- 打开 cross-encoder rerank 后，只重排候选，不创造资产。
- reranker 失败不影响 workflow 完成。
- LLM 失败不影响 workflow 完成。

### 5.10 验收命令

```powershell
conda activate midea
python -m unittest tests.test_retrieval_llm_enhancer
python -m unittest tests.test_retrieval_cross_encoder_rerank
python -m unittest tests.test_phase2_retrieval_agent
python -m unittest tests.test_phase2_retrieval_bundle
```

---

## 6. 工作包 B：Subsystem LLM 接口适配

### 6.1 目标

提升 `subsystem_plan_map` 质量，尤其是以下字段：

- `implementation_mode`
- `template_binding`
- `template_interface_bindings`
- `imported_signals`
- `exported_signals`
- `node_instances`
- `edges`
- `unresolved_items`

这是最重要的 LLM 增强点，因为它离最终 JSON 最近，又还处在 IR 层，可以被后续 `GlobalAssembler`、`CodingAgent`、`VerifierAgent` 收口。

### 6.2 修改文件

- `config.py`
- `agents/subsystem_planner.py`
- 新增 `agents/llm_enhancers/subsystem_interface_adapter.py`
- `tests/test_phase3_subsystem_planner.py`
- 新增 `tests/test_subsystem_llm_adapter.py`

### 6.3 调用位置

推荐在两个位置接入：

1. `_plan_template_reuse()` 前：对选中模板做端口语义适配。
2. `_plan_atomic_fallback()` 前：如果模板不匹配，让 LLM 判断是否真的需要 fallback，或是否存在更好的候选模板。

不要让 LLM 直接绕过 `_analyze_template_interface()`。

推荐流程：

```text
ArchitecturePlanner 给出 preferred_template_ids
-> SubsystemPlanner 找到 template_doc
-> 规则生成初始 interface_bindings
-> LLM InterfaceAdapter 输出 port_binding_patch / signal_aliases
-> 本地代码应用 patch
-> 再跑 _analyze_template_interface()
-> 通过则 reuse_template
-> 不通过则 atomic_fallback 或 unresolved_items
```

### 6.4 输入

```json
{
  "requirement_spec": {
    "system_type": "",
    "signals": {},
    "global_modes": [],
    "acceptance_criteria": []
  },
  "subsystem_descriptor": {
    "subsystem_id": "",
    "subsystem_type": "",
    "goal": "",
    "imports": [],
    "exports": [],
    "interface_bindings": []
  },
  "template_contract": {
    "template_id": "",
    "template_name": "",
    "template_role": "",
    "inputs": [],
    "outputs": [],
    "ports_definition": {},
    "compile_hints": {}
  },
  "shared_signal_registry": [],
  "available_atomic_modules": []
}
```

第一轮要控制上下文：

- `available_atomic_modules` 只给 `module_type/name/description/ports_summary`。
- 不给完整 `internal_flow_objects`。
- 不给完整最终 JSON 样本。

### 6.5 输出

```python
class PortBindingPatch(BaseModel):
    direction: str
    port_index: int
    template_port_name: str = ""
    signal_name: str
    signal_key: str = ""
    binding_kind: str
    allowed_external: bool = False
    owner_subsystem_id: str = ""
    confidence: float = 0.0
    reason: str = ""

class SubsystemInterfaceAdvice(BaseModel):
    subsystem_id: str
    selected_template_id: str = ""
    port_binding_patch: list[PortBindingPatch] = Field(default_factory=list)
    signal_aliases: dict[str, str] = Field(default_factory=dict)
    missing_bindings: list[str] = Field(default_factory=list)
    fallback_required: bool = False
    fallback_reason: str = ""
    risk_flags: list[str] = Field(default_factory=list)
```

### 6.6 采用规则

必须校验：

- `subsystem_id` 必须等于当前子系统。
- `selected_template_id` 为空或等于候选模板 ID。
- `direction` 只能是 `input` 或 `output`。
- `port_index` 必须在模板端口范围内。
- `binding_kind` 只能使用已有枚举：
  - `external_input`
  - `subsystem_output`
  - `shared_signal`
  - `global_mode`
- `signal_name` 不能为空。
- `confidence < 0.5` 的 patch 不采用，只写入 advisory。

应用后必须再次调用本地规则：

- 端口数量检查。
- shared signal registry 检查。
- `_analyze_template_interface()`。
- `VerifierAgent` 最终检查。

### 6.7 写回位置

写入每个子系统：

```json
{
  "template_binding": {
    "template_id": "",
    "reasoning": "",
    "llm_advisory": {
      "enabled": true,
      "adopted": true,
      "model": "",
      "patch_count": 0,
      "risk_flags": [],
      "fallback_reason": ""
    }
  }
}
```

同时在 `selection_reason` 或 `degrade_reason` 中保留最终采用原因。

### 6.8 测试

新增测试：

- 送风机标准控制模板：LLM 把“送风机启停自动命令”绑定到正确输入端口。
- 冷水阀模板：LLM 区分 `送风温度`、`送风温度设定值`、`冷水阀开度最终控制命令`。
- CO2 风阀模板：LLM 区分新风阀和回风阀输出。
- LLM 输出越界 `port_index`，应被丢弃。
- LLM 输出不存在模板 ID，应被丢弃。
- LLM 要求 fallback，但规则模板完全匹配时，不强制 fallback，只记录 risk。
- LLM 失败时走 deterministic 当前路径。

### 6.9 完成标准

- 默认关闭时 `test_phase3_subsystem_planner` 全部通过。
- 打开后能在 fake LLM 测试中改变端口绑定。
- 所有采用的 patch 都经过本地端口和模板合同校验。
- `subsystem_plan_map` 不出现未注册 `module_type`。

### 6.10 验收命令

```powershell
conda activate midea
python -m unittest tests.test_subsystem_llm_adapter
python -m unittest tests.test_phase3_subsystem_planner
python -m unittest tests.test_phase3_workflow
```

---

## 7. 工作包 C：Architecture LLM Advisor

### 7.1 目标

提升系统级架构质量，包括：

- 页签是否完整。
- 子系统边界是否合理。
- 每个子系统是否优先复用正确模板。
- shared signal ownership 是否合理。
- global modes 是否进入正确页面和子系统。
- system pattern 是否被正确采用。

### 7.2 修改文件

- `config.py`
- `agents/architecture_planner.py`
- 新增 `agents/llm_enhancers/architecture_advisor.py`
- `tests/test_phase3_architecture_planner.py`
- 新增 `tests/test_architecture_llm_advisor.py`

### 7.3 调用位置

推荐在 `ArchitecturePlanner.plan()` 中：

```text
选中 system_pattern
-> 规则生成 pages / subsystem_slots / interface_bindings 初稿
-> LLM advisor 产出架构 patch
-> 本地代码过滤 patch
-> 重新构造 shared_signal_registry
-> 写入 decomposition_result / architecture_plan
```

注意：LLM advisor 不能替代 `_select_system_pattern()`、`_rank_template_candidates()` 和 `_build_shared_signal_registry()`，只能提供 patch。

### 7.4 输入

```json
{
  "requirement_spec": {
    "system_type": "",
    "scenario_summary": "",
    "subsystems": [],
    "signals": {},
    "required_pages": [],
    "global_modes": [],
    "ambiguities": [],
    "assumptions": []
  },
  "selected_system_pattern": {
    "pattern_id": "",
    "system_type": "",
    "required_pages": [],
    "optional_pages": [],
    "subsystem_slots": [],
    "style_guides": {}
  },
  "candidate_templates": [
    {
      "template_id": "",
      "template_name": "",
      "template_role": "",
      "ports_summary": ""
    }
  ],
  "deterministic_draft": {
    "pages": [],
    "subsystem_descriptors": [],
    "subsystem_slots": [],
    "shared_signal_registry": []
  }
}
```

### 7.5 输出

```python
class ArchitectureAdvice(BaseModel):
    page_patch: list[dict] = Field(default_factory=list)
    subsystem_patch: list[dict] = Field(default_factory=list)
    template_preferences: dict[str, list[str]] = Field(default_factory=dict)
    shared_signal_patch: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    confidence: float = 0.0
```

### 7.6 采用规则

页面 patch：

- `page_id` 使用现有 `make_page_id()` 生成。
- `label` 不能为空。
- 不允许删除 deterministic draft 中已有必需页。
- 可新增 `IO/通讯`、`控制`、`定时`、`状态`、`故障`、`直膨机状态`、`直膨机故障` 等标准页。

子系统 patch：

- 不允许删除用户显式要求的子系统。
- 可调整 `page_id`、`priority`、`preferred_templates`。
- `preferred_templates` 必须存在于候选模板。

shared signal patch：

- 必须能对应已有 `imports/exports` 或 requirement signals。
- 如果出现多 owner，不能强行采用，写入 `warnings` 或 `review_required` 候选。

### 7.7 写回位置

- `architecture_plan.pattern_bindings[*].llm_advisory`
- `architecture_plan.warnings`
- `decomposition_result.warnings`
- `subsystem_slots[*].score_breakdown` 中可追加 advisory score

### 7.8 测试

新增测试：

- 输入 AHU + 直膨状态需求，LLM 建议补 `直膨机状态` 页，采用成功。
- 输入送风机 + 冷水阀 + 电加热，LLM 建议模板排序，最终 template IDs 必须来自候选。
- LLM 建议删除 `控制` 页，必须拒绝。
- LLM 建议不存在模板 ID，必须拒绝。
- LLM 输出 shared signal 多 owner，进入 warnings，不直接采用。

### 7.9 完成标准

- 默认关闭时架构规划行为不变。
- 打开后能通过 fake LLM 改善 page / subsystem / template preference。
- patch 被拒绝时有诊断。
- 不引入不在候选集的 template 或 pattern。

### 7.10 验收命令

```powershell
conda activate midea
python -m unittest tests.test_architecture_llm_advisor
python -m unittest tests.test_phase3_architecture_planner
python -m unittest tests.test_phase3_workflow
```

---

## 8. 工作包 D：Verification LLM Semantic Critic

### 8.1 目标

在 deterministic verifier 之后，增加业务语义复核层。它不替代结构校验，只补足以下判断：

- AHU 标准页签覆盖是否合理。
- 风机控制是否包含运行、故障、可用、启停最终命令。
- PID 回路是否包含设定值、反馈值、P/I/D、死区、计算间隔、上下限。
- 阀门控制是否包含手自动、手动命令、自动命令、最终命令、上下限。
- 电加热是否包含故障、控制使能、分级输出或预热输出。
- 直膨机状态/故障是否有对应点位或页面。
- 命名、页面组织和目标样例是否明显不一致。

### 8.2 修改文件

- `config.py`
- `agents/verifier_agent.py`
- 新增 `agents/llm_enhancers/semantic_verifier.py`
- `utils/graph_ir.py`，可选扩展 `VerificationMetrics`
- `tests/test_phase3_verifier_native_contract.py`
- 新增 `tests/test_semantic_verifier_llm.py`

### 8.3 调用位置

在 `VerifierAgent.verify()` 末尾：

```text
先执行 deterministic verifier
-> 如果结构错误存在，可跳过 LLM semantic critic
-> 如果结构 passed 或只有 warning，调用 LLM critic
-> LLM critic 输出 semantic_warnings / semantic_issues
-> 第一轮只写 warnings
```

第一轮建议：LLM semantic critic 不改变 `verification_report.status`。

第二轮再考虑：

- 高置信、明确缺失的 AHU 业务项升级为 `severity=warning` issue。
- 对 `acceptance_criteria` 明确要求但缺失的项，升级为 `error`。

### 8.4 输入

不要把完整 900+ flow_objects 全塞给 LLM。先构造摘要：

```json
{
  "requirement_spec": {},
  "architecture_summary": {
    "pages": [],
    "subsystem_slots": [],
    "global_constraints": []
  },
  "subsystem_summary": [
    {
      "subsystem_id": "",
      "implementation_mode": "",
      "template_id": "",
      "imported_signals": [],
      "exported_signals": [],
      "node_types": []
    }
  ],
  "compiled_summary": {
    "page_labels": [],
    "subflow_names": [],
    "node_type_counts": {},
    "compile_report": {}
  },
  "deterministic_verification": {
    "status": "",
    "issues": [],
    "warnings": []
  }
}
```

### 8.5 输出

```python
class SemanticFinding(BaseModel):
    severity: str
    category: str
    target_id: str = ""
    message: str
    suggested_fix: str = ""
    confidence: float = 0.0

class SemanticVerificationResult(BaseModel):
    findings: list[SemanticFinding] = Field(default_factory=list)
    coverage_summary: dict[str, Any] = Field(default_factory=dict)
    risk_flags: list[str] = Field(default_factory=list)
```

### 8.6 采用规则

第一轮：

- 所有 findings 写入 `verification_report.warnings`。
- `severity=error` 也不改变最终 status，只标记为 `semantic_error_candidate`。
- 记录 `confidence`，低于 0.6 的 finding 不进入 warnings，只进入 trace advisory。

第二轮：

- 对需求明确项缺失，可升级为正式 `VerificationIssue`。

### 8.7 测试

新增测试：

- fake LLM 检出“风机缺少故障标志”，写入 warnings。
- deterministic verifier 已有 error 时，默认跳过 semantic critic。
- LLM 输出低置信 finding，不进入 warnings。
- LLM 输出 malformed JSON，回退且不影响 status。

### 8.8 完成标准

- 默认关闭时 verifier 行为完全不变。
- 打开后能生成 `semantic_warnings`。
- 不影响 `repair_router` 主判定。
- trace 能看到 semantic critic 是否启用、模型、耗时、finding 数量。

### 8.9 验收命令

```powershell
conda activate midea
python -m unittest tests.test_semantic_verifier_llm
python -m unittest tests.test_phase3_verifier_native_contract
python -m unittest tests.test_phase4_workflow_repair_loop
```

---

## 9. 工作包 E：Global Assembly 语义补洞

### 9.1 目标

只在 `GlobalAssembler` 产生 planning / assembly 级 `unresolved_items` 时调用 LLM，给出候选 shared signal 绑定。默认不启用。

### 9.2 使用场景

- `ambiguous_shared_signal`
- `shared_signal_owner_mismatch`
- `missing_exporter`
- `synthetic_shared_signal_source`

### 9.3 输出

```python
class AssemblyResolutionAdvice(BaseModel):
    signal_key: str
    owner_subsystem_id: str = ""
    candidate_exporters: list[str] = Field(default_factory=list)
    allowed_external: bool = False
    reason: str = ""
    confidence: float = 0.0
```

### 9.4 采用规则

- `owner_subsystem_id` 必须存在于 `subsystem_plan_map`。
- `candidate_exporters` 必须来自 `shared_signal_registry` 或 `subsystem_plan_map`。
- `confidence < 0.75` 不自动采用。
- 采用后仍由 `VerifierAgent` 检查。

### 9.5 建议顺序

本工作包不放在第一批。只有当 A 到 D 稳定后，且真实 trace 中 unresolved shared signal 高频出现，再开工。

---

## 10. 工作包 F：RepairAgent LLM Advisory

### 10.1 目标

当 `RepairAgent` 遇到 unsupported issue 或 patch 失败时，让 LLM 生成解释性修复建议，辅助后续开发扩展 deterministic repair。

### 10.2 约束

- 不让 LLM 直接修改 `architecture_plan`、`subsystem_plan_map`、`assembled_graph_ir`。
- 不让 LLM 修改 `compiled_artifact`。
- 只写入 `repair_context.patch_instructions` 或 `repair_history[*].llm_advisory`。

### 10.3 建议顺序

该工作包排在最后。先积累真实失败桶，再决定是否值得做。

---

## 11. LangGraph 恢复和幂等性要求

官方 durable execution 文档强调，启用 checkpointer 后可以恢复执行，但非确定性操作和副作用应设计为确定性、幂等，或封装为 task，避免恢复时重复执行带来不同结果。

当前工作流已有 HITL 节点，`interrupt()` 恢复时节点会从头重新运行。新增 LLM 调用时要遵守以下规则：

### 11.1 不在 interrupt 前做不可重放 LLM 调用

已有 review 节点里不要插入 LLM 调用。原因：

- `interrupt()` 恢复时节点会从头执行。
- 如果 LLM 调用在 `interrupt()` 之前，恢复后可能重复调用并生成不同结果。

本方案不改 `clarification_review` 和 `architecture_review` 的 LLM 逻辑。

### 11.2 LLM 结果写入 state 后再进入下游

每个增强节点应在同一次节点执行中完成：

```text
调用 LLM
-> 归一化
-> 写入当前节点输出对象 metadata / advisory
-> 下游消费确定结果
```

不要让下游节点重新调用同一个 LLM 逻辑。

### 11.3 Trace 必须记录 fallback

每次 LLM 增强都记录：

- `enabled`
- `provider`
- `model`
- `elapsed_ms`
- `structured_output_used`
- `adopted`
- `fallback_used`
- `fallback_reason`
- `input_summary_hash`
- `output_summary_hash`

第一轮可以只写 metadata 和 trace summary，不要求完整 token 统计。

---

## 12. Trace 和诊断

### 12.1 编译诊断继续保留

继续依赖：

- `compiled_artifact.compile_report.body_node_count`
- `dropped_node_count`
- `missing_template_count`
- `unresolved_placeholder_count`
- `body_expansion_errors`
- `VerifierAgent` strict compile hard fail

LLM 增强不能削弱这些字段。

### 12.2 新增 LLM 诊断摘要

建议在 `workflow_trace.py` 的 summary 中增加：

```json
{
  "llm_enhancement": {
    "enabled_nodes": [],
    "fallback_count": 0,
    "adopted_patch_count": 0,
    "semantic_warning_count": 0,
    "model_usage": [
      {
        "node": "",
        "provider": "",
        "model": "",
        "elapsed_ms": 0,
        "fallback_used": false
      }
    ]
  }
}
```

### 12.3 API 投影

第一轮不要求前端展示细节，只在 API diagnostics 中可选追加：

- `llm_enhancement_enabled`
- `llm_fallback_count`
- `semantic_warning_count`

不要返回完整 prompt 或完整 LLM 输出。

---

## 13. 推荐实施顺序

按以下顺序开工：

1. 工作包 A0：`analysis` LLM engineering requirement compiler。
2. 工作包 A：`retrieval` LLM rewrite + Cross-Encoder rerank。
3. 工作包 B：`subsystem_planning` LLM interface adapter。
4. 工作包 C：`architecture_planning` LLM advisor。
5. 工作包 D：`verification` LLM semantic critic。
6. 工作包 E：`global_assembly` unresolved 语义补洞。
7. 工作包 F：`repair_agent` LLM advisory。

原因：

- `analysis` 是后续所有节点的语义事实入口，必须先把需求编译成更完整的工程规范。
- `retrieval` 和 `subsystem_planning` 对最终 JSON 质量影响最大，且能用资产白名单约束。
- `architecture_planning` 价值高，但要更小心 shared signal 和页面结构 patch。
- `verification` critic 能提升发现问题能力，但第一轮不应直接改变 status。
- `global_assembly` 和 `repair_agent` 更适合等真实失败桶稳定后再做。

---

## 14. 第一批最小闭环

如果只做一批，建议做 A0 + A + B：

```text
Analysis LLM engineering compiler
-> 更完整的 requirement_spec / clarification_signals
-> Retrieval LLM rewrite + Cross-Encoder rerank
-> 更稳定命中 AHU templates / patterns
-> Subsystem LLM interface adapter
-> 更好绑定模板端口和信号
-> 原有 GlobalAssembler
-> 原有 CodingAgent
-> 原有 VerifierAgent
```

第一批验收目标：

- 对“生成一个 AHU 空调箱 Node-RED flows JSON，包含 IO/通讯、控制、定时、直膨机状态...”这类复杂需求：
  - `requirement_spec.engineering.points/control_loops/interlocks` 有结构化内容。
  - `analysis_result.clarification_signals` 能指出缺少点表、设备数量、通讯地址等关键风险。
  - `retrieval_bundle.metadata.top_subflow_template_ids` 命中送风机、冷水阀、电加热、风阀、直膨相关模板。
  - `subsystem_plan_map` 中更多子系统走 `reuse_template`。
  - `template_binding.llm_advisory.adopted=true` 的 patch 数量可见。
  - `compile_report.missing_template_count=0`。
  - `compile_report.unresolved_placeholder_count=0`。
  - `verification_report.status` 不比基线更差。

---

## 15. 测试策略

### 15.1 单元测试

必须使用 fake LLM：

- 不依赖真实 API。
- 不依赖网络。
- 输出固定结构。
- 可模拟超时、异常、malformed JSON、非法 ID。

推荐测试文件：

```text
tests/test_retrieval_llm_enhancer.py
tests/test_subsystem_llm_adapter.py
tests/test_architecture_llm_advisor.py
tests/test_semantic_verifier_llm.py
```

### 15.2 合同测试

现有合同测试必须继续通过：

```powershell
conda activate midea
python -m unittest discover -s tests -p "test_phase2*.py"
python -m unittest discover -s tests -p "test_phase3*.py"
python -m unittest discover -s tests -p "test_phase4*.py"
python -m unittest tests.test_platform_flow_schema
python -m unittest tests.test_coding_subflow_body_expansion
```

### 15.3 真实链路 smoke

新增脚本建议：

```text
scripts/run_llm_enhancement_smoke.py
```

支持参数：

```powershell
conda activate midea
python scripts/run_llm_enhancement_smoke.py --case ahu_complex --nodes retrieval,subsystem --fake-llm
python scripts/run_llm_enhancement_smoke.py --case ahu_complex --nodes retrieval,subsystem --real-llm
```

fake LLM 是 CI 必跑；real LLM 只本地或人工验收跑。

### 15.4 指标对比

对比打开/关闭 LLM：

| 指标 | 说明 |
| --- | --- |
| retrieved_subflow_count | 子流程模板召回数 |
| top_subflow_template_ids | top 模板是否覆盖目标子系统 |
| reuse_template_count | `subsystem_plan_map` 中复用模板数量 |
| atomic_fallback_count | 降级数量 |
| unresolved_item_count | IR 未解决项数量 |
| body_node_count | body 展开数量 |
| missing_template_count | strict compile 错误 |
| verification_status | 最终验收状态 |
| semantic_warning_count | LLM critic 语义告警 |

---

## 16. 回滚策略

所有 LLM 增强必须可以通过环境变量关闭。

回滚方式：

```powershell
conda activate midea
$env:LLM_ENHANCEMENT_ENABLED="false"
$env:RETRIEVAL_USE_LLM_REWRITE="false"
$env:RETRIEVAL_USE_CROSS_ENCODER_RERANK="false"
$env:ARCHITECTURE_USE_LLM_ADVISOR="false"
$env:SUBSYSTEM_USE_LLM_ADAPTER="false"
$env:VERIFICATION_USE_LLM_CRITIC="false"
```

回滚后应恢复当前 deterministic 基线：

```powershell
conda activate midea
python -m unittest discover -s tests -p "test_phase*.py"
python -m unittest tests.test_workflow_api
```

如果某个 LLM 节点导致质量下降，只关闭对应节点，不需要整体回滚。

---

## 17. 文件级开工清单

### 17.1 第一批 A0 + A + B

新增：

```text
agents/llm_enhancers/__init__.py
agents/llm_enhancers/base.py
agents/llm_enhancers/analysis_engineering_compiler.py
agents/llm_enhancers/retrieval_rewrite.py
agents/llm_enhancers/subsystem_interface_adapter.py
utils/reranker_manager.py
utils/retrieval_rerank.py
tests/test_analysis_engineering_compiler.py
tests/test_retrieval_llm_enhancer.py
tests/test_retrieval_cross_encoder_rerank.py
tests/test_subsystem_llm_adapter.py
```

修改：

```text
config.py
agents/analysis_agent.py
agents/retrieval_agent.py
agents/subsystem_planner.py
utils/phase3_adapters.py
workflow_trace.py
```

可选修改：

```text
app/services/workflow_state_projection.py
app/api/models.py
frontend/src/types/workflow.ts
```

第一批不建议改前端，除非需要展示诊断。

### 17.2 第二批 C + D

新增：

```text
agents/llm_enhancers/architecture_advisor.py
agents/llm_enhancers/semantic_verifier.py
tests/test_architecture_llm_advisor.py
tests/test_semantic_verifier_llm.py
```

修改：

```text
agents/architecture_planner.py
agents/verifier_agent.py
utils/graph_ir.py
workflow_trace.py
```

---

## 18. 代码实现约束

### 18.1 结构化输出

优先使用：

```python
structured_llm = llm.with_structured_output(ModelClass, method="function_calling")
```

失败后可回退 JSON 解析，但必须经过 Pydantic 校验。

### 18.2 Prompt 约束

每个 prompt 必须写清：

- 只能使用输入中给定的候选资产。
- 不允许输出最终平台 JSON。
- 不允许发明 `template_id` / `module_type`。
- 输出必须是指定 schema。
- 不确定时写入 `risk_flags` 或 `fallback_required`。

### 18.3 输出归一化

每个 enhancer 都要有本地 normalize：

```python
def normalize_advice(payload: Any, allowed_ids: set[str]) -> dict:
    ...
```

不要在主 planner 中散落 LLM 输出清洗逻辑。

### 18.4 注释

新增代码注释按仓库要求使用中文，必要英文术语除外。

---

## 19. 完成定义

第一批完成定义：

- 新增 LLM retrieval rewrite，默认关闭。
- 新增 Cross-Encoder retrieval rerank，默认关闭。
- 新增 LLM subsystem interface adapter，默认关闭。
- LLM 节点支持 fake LLM 单测，reranker 支持 fake scorer 单测。
- LLM 输出只能影响查询改写或结构化 IR patch，不能生成最终 JSON。
- 候选排序由专用 reranker / rule score 完成，不由通用 LLM 直接排序。
- LLM 输出非法时自动 fallback。
- 开关关闭时所有现有测试通过。
- 打开 fake LLM / fake reranker 时，能证明查询改写、模板排序和端口绑定发生可控变化。
- trace 或 metadata 中能看到 enabled、adopted、fallback。

第二批完成定义：

- `architecture_planning` 支持 LLM patch，但不删除必需页和显式子系统。
- `verification` 支持 LLM semantic critic，但第一轮不改变 status。
- real LLM smoke 至少跑通一个复杂 AHU 查询。
- 输出质量指标与 baseline 对比有记录。

---

## 20. 总体验收命令

第一批：

```powershell
conda activate midea
python -m unittest tests.test_analysis_engineering_compiler
python -m unittest tests.test_retrieval_llm_enhancer
python -m unittest tests.test_retrieval_cross_encoder_rerank
python -m unittest tests.test_subsystem_llm_adapter
python -m unittest discover -s tests -p "test_phase2*.py"
python -m unittest discover -s tests -p "test_phase3*.py"
python -m unittest tests.test_platform_flow_schema
python -m unittest tests.test_coding_subflow_body_expansion
python -m compileall app workflow.py workflow_trace.py agents utils tests scripts
```

第二批：

```powershell
conda activate midea
python -m unittest tests.test_architecture_llm_advisor
python -m unittest tests.test_semantic_verifier_llm
python -m unittest discover -s tests -p "test_phase4*.py"
python -m unittest tests.test_workflow_api
python scripts/run_phase6_real_query_suite.py
```

全量回归：

```powershell
conda activate midea
python -m unittest discover -s tests
python -m compileall app workflow.py workflow_trace.py agents utils tests scripts
python -m pip check
```

---

## 21. 下次开工建议

下次开工时建议直接从第一批开始：

1. 建 `agents/llm_enhancers/base.py`，封装模型初始化、结构化输出、fallback、诊断摘要。
2. 实现 `analysis_engineering_compiler.py`。
3. 在 `AnalysisAgent.__call__()` 中用开关接入工程需求补丁，保持现有 `AnalysisResult` 和 fallback。
4. 写 `tests/test_analysis_engineering_compiler.py`。
5. 实现 `retrieval_rewrite.py`。
6. 实现 `utils/reranker_manager.py` 和 `utils/retrieval_rerank.py`，默认使用 `BAAI/bge-reranker-v2-m3`，测试使用 fake scorer。
7. 在 `RetrievalAgent.retrieve_bundle()` 中用开关接入，不改正式 bundle schema。
8. 写 `tests/test_retrieval_llm_enhancer.py` 和 `tests/test_retrieval_cross_encoder_rerank.py`。
9. 实现 `subsystem_interface_adapter.py`。
10. 在 `SubsystemPlanner._plan_template_reuse()` 前接入 adapter。
11. 写 `tests/test_subsystem_llm_adapter.py`。
12. 补 trace summary 中的 LLM / reranker 增强诊断。
13. 跑第一批验收命令。

不要先做 `verification` critic 或 `repair_agent` LLM advisory。当前收益最大的路径是先提高需求结构化质量、召回质量和子系统接口绑定质量。
