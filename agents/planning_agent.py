"""
规划智能体 (Planning Agent)
职责：拥有控制逻辑专家的思维，将需求转化为逻辑步骤
"""
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
import config
from utils.context_formatter import format_docs_for_planner
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


# ==================== 规划智能体 ====================


class PlanningAgent:
    """规划智能体"""
    
    def __init__(self, llm_provider: Optional[str] = None):
        """初始化 LLM
        
        Args:
            llm_provider: LLM 提供商,如不指定则使用配置文件中的默认值
        """
        # 初始化 LLM
        self.llm = LLMManager.get_llm(llm_provider)
        
        # 创建提示词模板
        self.planning_prompt = self._create_planning_prompt()
        
        if config.DEBUG:
            print(f"✅ 规划智能体初始化完成")
            print(f"   LLM 提供商: {llm_provider or config.LLM_PROVIDER}")
    
    def _create_planning_prompt(self) -> ChatPromptTemplate:
        """创建规划提示词模板"""
        system_prompt = """
你是一个工业自动化控制系统的逻辑规划专家。你的任务是根据用户的自然语言需求,使用提供的模块(积木)设计一个逻辑控制图。

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
    
    def plan(self, user_query: str, retrieval_context: Dict[str, Any]) -> PlanIR:
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
        
        # 清洗检索上下文为轻量级文本
        slim_context = format_docs_for_planner(retrieval_context)
        
        if config.DEBUG:
            print(f"   清洗后上下文大小: {len(slim_context)} 字符")
        
        # 构建 prompt
        messages = self.planning_prompt.format_messages(
            user_query=user_query,
            slim_context=slim_context
        )
        
        # 调用 LLM 生成 JSON 输出
        try:
            response = self.llm.invoke(messages)
            
            # 解析 JSON 字符串
            import json
            import re
            
            # 提取 JSON 内容(处理可能的markdown代码块)
            content = response.content
            json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # 尝试直接解析
                json_str = content.strip()
            
            # 解析为字典
            plan_dict = json.loads(json_str)
            
            # 转换为 PlanIR 对象
            plan_ir = PlanIR(**plan_dict)
            
            # 验证节点ID的有效性
            plan_ir.validate_ids()
            
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
        
        except Exception as e:
            if config.DEBUG:
                print(f"\n❌ 规划失败: {e}")
                import traceback
                traceback.print_exc()
            
            # 返回空规划
            return PlanIR(
                goal="规划失败",
                nodes=[],
                connections=[]
            )
    
    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        LangGraph 节点调用接口
        
        Args:
            state: 当前工作流状态
            
        Returns:
            更新后的状态
        """
        user_query = state.get("user_query", "")
        retrieval_context = state.get("retrieval_context", {})
        
        # 生成规划
        plan_ir = self.plan(user_query, retrieval_context)
        
        # 将 PlanIR 转换为字典存入状态
        state["execution_plan"] = plan_ir.model_dump()
        state["current_step"] = "planning_completed"
        
        return state
