"""
规划智能体 (Planning Agent)

状态:
- 正式主链: 否。Phase 3 正式规划链已切换为
  ArchitecturePlanner -> SubsystemPlanner -> GlobalAssembler。
- 当前用途: 保留为旧 execution_plan compat planner，仍被 Phase 2 bundle
  consumers / compat 回归测试直接覆盖。
- 迁移计划: 等 compat 调用方清退后，再评估迁移到 legacy/ 目录。
"""
import json
import re
from typing import Dict, List, Any, Optional, Set
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
import config
from utils.console_utils import safe_print as print
from utils.context_formatter import format_docs_for_planner
from utils.retrieval_bundle_utils import build_allowed_module_types
from utils.model_manager import LLMManager


# ==================== 数据结构定义 ====================

class PlanNode(BaseModel):
    """规划图中的单个节点(模块实例)"""
    logic_id: str = Field(..., description="唯一的逻辑ID,使用有意义的名称,如 'temp_diff_calc'")
    module_type: str = Field(..., description="对应检索结果中的 module_type")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="需要配置的参数键值对")
    reasoning: str = Field(..., description="选择该模块的简短理由")


class PlanConnection(BaseModel):
    """规划图中的连接(数据流)"""
    from_node: str = Field(..., description="上游节点的 logic_id")
    from_port_index: int = Field(0, description="上游节点的输出端口索引(0-based)")
    to_node: str = Field(..., description="下游节点的 logic_id")
    to_port_index: int = Field(..., description="下游节点的输入端口索引(0-based)")


class PlanIR(BaseModel):
    """规划智能体的中间表示(Intermediate Representation)"""
    goal: str = Field(..., description="对当前计算任务的简述")
    nodes: List[PlanNode] = Field(..., description="模块节点列表")
    connections: List[PlanConnection] = Field(..., description="模块间的连接关系")
    
    def validate_ids(self) -> None:
        """验证连接中的节点ID是否存在"""
        node_ids = {n.logic_id for n in self.nodes}
        for conn in self.connections:
            if conn.from_node not in node_ids:
                raise ValueError(f"连接中引用了不存在的上游节点ID: {conn.from_node}")
            if conn.to_node not in node_ids:
                raise ValueError(f"连接中引用了不存在的下游节点ID: {conn.to_node}")
    
    def validate_module_types(self, available_types: Set[str]) -> List[str]:
        """验证所有节点的 module_type 是否在可用模块白名单中
        
        Args:
            available_types: 检索结果中包含的合法 module_type 集合
            
        Returns:
            不合法的 module_type 列表（空列表表示全部合法）
            
        Raises:
            ValueError: 当存在不合法的 module_type 时
        """
        invalid = []
        for node in self.nodes:
            if node.module_type not in available_types:
                invalid.append(f"{node.logic_id} -> {node.module_type}")
        if invalid:
            raise ValueError(
                f"以下节点使用了不在检索结果中的 module_type: {', '.join(invalid)}。"
                f"可用类型: {sorted(available_types)}"
            )
        return invalid


# ==================== 规划智能体 ====================


class PlanningAgent:
    """旧主链 compat planner，不是当前 Phase 3 正式规划节点。"""
    
    def __init__(self, llm_provider: Optional[str] = None, model: Optional[str] = None):
        """初始化 LLM
        
        Args:
            llm_provider: LLM 提供商,如不指定则使用配置文件中的默认值
            model: 指定模型名称,如不指定则使用对应提供商的默认模型
        """
        provider = llm_provider or config.PLANNING_LLM_PROVIDER or config.LLM_PROVIDER
        model_name = model or config.PLANNING_LLM_MODEL or None

        # 初始化 LLM
        self.llm = LLMManager.get_llm(
            provider,
            model=model_name,
            temperature=config.PLANNING_LLM_TEMPERATURE,
        )
        
        # 创建提示词模板
        self.planning_prompt = self._create_planning_prompt()
        
        if config.DEBUG:
            print(f"✅ 规划智能体初始化完成")
            print(f"   LLM 提供商: {provider}")
            print(f"   温度: {config.PLANNING_LLM_TEMPERATURE}")
            if model_name:
                print(f"   指定模型: {model_name}")
    
    def _create_planning_prompt(self) -> ChatPromptTemplate:
        """创建规划提示词模板"""
        system_prompt = """
你是一个工业自动化控制系统的逻辑规划专家。你的任务是根据用户的自然语言需求,使用提供的模块(积木)设计一个逻辑控制图。

### 业务场景参考:
{analysis_context}

### 你的任务:
1. 分析用户的计算公式或控制逻辑。
2. 从【可用模块列表】中选择合适的模块。**严禁虚构模块**,只能使用列表中的 module_type。
3. 规划每个模块的参数(如乘法模块的输入数量、常量的数值)。
4. 定义模块之间的连接关系(拓扑结构)。

### 规则:
- **逻辑ID**:为每个模块起一个唯一的、有意义的 ID(如 `input_temp`, `calc_diff`)。
- **端口索引**:输入输出端口必须使用 0-based 索引(如 0 代表第一个端口)。
- **常量处理**:如果公式中有常数(如 4.18),请检查模块是否支持直接设置参数(如 fixedValue),如果不支持,则需要实例化一个 `constInput` 模块。
- **参数配置**:确保 `parameters` 字段中的键名与模块定义中的参数名完全一致。
- **参数类型**:注意参数的类型(integer, number, boolean, string),确保类型正确。
- **端口连接**:仔细检查端口索引,确保连接正确(输出端口连接到输入端口)。
- **业务场景参考**:它只用于帮助你理解需求,不能替代【可用模块列表】。最终只能使用可用模块列表中的 module_type。
- **Phase 2 规划优先级**:
  - 先参考 `system_patterns` 里的页面/布局提示，帮助确定规划倾向。
  - 优先复用 `subflow_templates`，只有模板不足以覆盖需求时，才退化为 `atomic_modules` 组合。
  - `system_patterns` 只是 prompt hint，不是新的硬输出 schema；你的输出仍必须严格遵循既定 `execution_plan` JSON 结构。

### 可用模块列表:
{slim_context}

### 输出格式:
你必须严格按照以下 JSON 格式输出,不要添加任何额外的文本:

```json
{{
  "goal": "简要描述本次规划的目标",
  "nodes": [
    {{
      "logic_id": "节点唯一ID",
      "module_type": "模块类型",
      "name": "模块实例名称",
      "parameters": {{"参数名": "参数值"}},
      "reasoning": "选择此模块的理由"
    }}
  ],
  "connections": [
    {{
      "from_node": "上游节点ID",
      "from_port_index": 0,
      "to_node": "下游节点ID",
      "to_port_index": 0
    }}
  ]
}}
```
"""
        
        user_template = """用户需求:{user_query}

请根据上述需求和可用模块,设计一个完整的逻辑控制图。

记住:必须严格输出 JSON 格式,不要添加任何解释性文本。"""
        
        return ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", user_template)
        ])

    def _build_retry_messages(
        self,
        user_query: str,
        slim_context: str,
        analysis_context: str,
        error_message: str,
        previous_output: str,
    ):
        """构建带错误反馈的重试消息"""
        retry_prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                """
你是一个工业自动化控制系统的逻辑规划专家。你需要修正上一版规划输出中的错误。

请严格遵守以下规则：
1. 只能使用【可用模块列表】中的 module_type。
2. parameters 中的键名必须与模块定义完全一致。
3. 连接中的节点 ID 必须全部存在。
4. 端口索引必须使用 0-based。
5. 输出必须是完整、可解析的 JSON，不要添加解释性文本。

【可用模块列表】
{slim_context}

【业务场景参考】
{analysis_context}
""",
            ),
            (
                "user",
                """用户需求：{user_query}

你之前的规划输出存在以下问题：
{error_message}

你之前的输出：
{previous_output}

请修正后重新输出完整 JSON。""",
            ),
        ])

        return retry_prompt.format_messages(
            user_query=user_query,
            slim_context=slim_context,
            analysis_context=analysis_context,
            error_message=error_message,
            previous_output=previous_output,
        )

    def _format_analysis_context(self, analysis_result: Optional[Dict[str, Any]]) -> str:
        if not isinstance(analysis_result, dict):
            return "无额外业务场景参考。"

        scenario = analysis_result.get("scenario_analysis", {})
        if not isinstance(scenario, dict):
            return "无额外业务场景参考。"

        lines = []
        summary = (scenario.get("summary", "") or "").strip()
        if summary:
            lines.append(f"- 业务摘要: {summary}")

        field_mappings = [
            ("business_goal", "业务目标"),
            ("system_type", "系统类型"),
            ("equipment_object", "设备对象"),
            ("actuator", "执行器"),
            ("controlled_variable", "被控量"),
            ("feedback_variable", "反馈量"),
            ("setpoint_variable", "设定值"),
            ("output_signal", "期望输出"),
            ("control_strategy", "控制策略"),
            ("control_mode", "控制模式"),
        ]
        for key, label in field_mappings:
            value = (scenario.get(key, "") or "").strip()
            if value:
                lines.append(f"- {label}: {value}")

        input_signals = scenario.get("input_signals", [])
        if isinstance(input_signals, list) and input_signals:
            lines.append(f"- 输入信号: {', '.join(str(item) for item in input_signals[:5])}")

        output_signals = scenario.get("output_signals", [])
        if isinstance(output_signals, list) and output_signals:
            lines.append(f"- 输出信号: {', '.join(str(item) for item in output_signals[:5])}")

        ambiguities = scenario.get("ambiguities", [])
        if isinstance(ambiguities, list) and ambiguities:
            lines.append(f"- 模糊点: {'; '.join(str(item) for item in ambiguities[:config.ANALYSIS_MAX_AMBIGUITIES])}")

        assumptions = scenario.get("assumptions", [])
        if isinstance(assumptions, list) and assumptions:
            lines.append(f"- 假设: {'; '.join(str(item) for item in assumptions[:config.ANALYSIS_MAX_ASSUMPTIONS])}")

        if not lines:
            return "无额外业务场景参考。"

        return "\n".join(lines)

    def _generate_plan(self, messages) -> PlanIR:
        """统一处理 structured output 和回退解析"""
        try:
            structured_llm = self.llm.with_structured_output(
                PlanIR,
                method="function_calling",
            )
            plan_ir = structured_llm.invoke(messages)
            if config.DEBUG:
                print("   ✅ Structured Output 解析成功")
            return plan_ir
        except Exception as e:
            if config.DEBUG:
                print(f"   ⚠️ Structured Output 失败，回退到正则解析: {e}")
            return self._fallback_parse(messages)

    def _validate_plan(self, plan_ir: PlanIR) -> None:
        """统一校验规划结果"""
        if not plan_ir.nodes:
            raise ValueError("规划结果为空：至少需要 1 个节点。")
        plan_ir.validate_ids()
        if self._available_module_types:
            plan_ir.validate_module_types(self._available_module_types)
    
    def plan(
        self,
        user_query: str,
        bundle_or_context: Dict[str, Any],
        analysis_result: Optional[Dict[str, Any]] = None,
    ) -> PlanIR:
        """
        生成执行计划
        
        Args:
            user_query: 用户需求
            retrieval_context: 检索到的完整上下文信息
            
        Returns:
            PlanIR: 结构化的规划中间表示
        """
        if config.DEBUG:
            print(f"\n🎯 规划智能体开始工作...")
            print(f"   用户需求: {user_query}")
        
        # 提取可用 module_type 白名单（用于后续校验）
        self._available_module_types = build_allowed_module_types(bundle_or_context)
        
        # 清洗检索上下文为轻量级文本
        slim_context = format_docs_for_planner(
            bundle_or_context,
            detail_top_n=config.PLANNING_CONTEXT_DETAIL_TOP_N,
            max_modules=config.PLANNING_CONTEXT_MAX_MODULES,
        )
        analysis_context = self._format_analysis_context(analysis_result)
        
        if config.DEBUG:
            print(f"   清洗后上下文大小: {len(slim_context)} 字符")
        
        # 构建 prompt
        messages = self.planning_prompt.format_messages(
            user_query=user_query,
            slim_context=slim_context,
            analysis_context=analysis_context,
        )

        plan_ir = None
        previous_output = ""
        last_error = None
        max_attempts = max(1, config.PLANNING_MAX_RETRIES)

        for attempt in range(1, max_attempts + 1):
            try:
                current_messages = messages
                if attempt > 1 and last_error is not None:
                    current_messages = self._build_retry_messages(
                        user_query=user_query,
                        slim_context=slim_context,
                        analysis_context=analysis_context,
                        error_message=last_error,
                        previous_output=previous_output,
                    )
                    if config.DEBUG:
                        print(f"   🔁 开始第 {attempt} 次规划修正")

                plan_ir = self._generate_plan(current_messages)
                self._validate_plan(plan_ir)
                break
            except Exception as error:
                last_error = str(error)
                if 'plan_ir' in locals() and isinstance(plan_ir, PlanIR):
                    previous_output = plan_ir.model_dump_json(ensure_ascii=False, indent=2)

                if attempt >= max_attempts:
                    if config.DEBUG:
                        print(f"\n❌ 规划失败: {error}")
                    return PlanIR(goal=f"规划失败: {error}", nodes=[], connections=[])

                if config.DEBUG:
                    print(f"   ⚠️ 第 {attempt} 次规划失败，准备重试: {error}")
        
        if config.DEBUG:
            print(f"\n✅ 规划完成:")
            print(f"   目标: {plan_ir.goal}")
            print(f"   节点数: {len(plan_ir.nodes)}")
            print(f"   连接数: {len(plan_ir.connections)}")
            
            # 显示节点列表
            print(f"\n   节点列表:")
            for node in plan_ir.nodes:
                print(f"     • {node.logic_id} ({node.module_type})")
            
            # 显示连接关系
            if plan_ir.connections:
                print(f"\n   连接关系:")
                for conn in plan_ir.connections:
                    print(f"     {conn.from_node}[{conn.from_port_index}] -> {conn.to_node}[{conn.to_port_index}]")
        
        return plan_ir
    
    def _fallback_parse(self, messages) -> PlanIR:
        """
        回退解析：当 Structured Output 不可用时，通过正则提取 JSON 手动解析
        
        Args:
            messages: 已格式化的 prompt 消息列表
            
        Returns:
            PlanIR: 解析后的规划中间表示
            
        Raises:
            ValueError: JSON 解析或 Pydantic 校验失败时
        """
        response = self.llm.invoke(messages)
        content = response.content
        
        # 提取 JSON 内容（处理可能的 markdown 代码块）
        json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # 尝试直接解析
            json_str = content.strip()
        
        plan_dict = json.loads(json_str)
        plan_ir = PlanIR(**plan_dict)
        
        if config.DEBUG:
            print(f"   ✅ 回退正则解析成功")
        
        return plan_ir
    
    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        LangGraph 节点调用接口
        
        Args:
            state: 当前工作流状态
            
        Returns:
            更新后的状态
        """
        user_query = state.get("user_query", "")
        bundle_or_context = state.get("retrieval_bundle") or state.get("retrieval_context", {})
        analysis_result = state.get("analysis_result", {})
        
        # 生成规划
        plan_ir = self.plan(user_query, bundle_or_context, analysis_result)
        
        # 将 PlanIR 转换为字典存入状态
        state["execution_plan"] = plan_ir.model_dump()
        state["current_step"] = "planning_completed"
        
        return state
