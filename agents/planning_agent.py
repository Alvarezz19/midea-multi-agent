"""
规划智能体 (Planning Agent)
职责：拥有控制逻辑专家的思维，将需求转化为逻辑步骤
"""
from typing import Dict, List, Any
from langchain.chat_models import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
import config


class PlanningAgent:
    """规划智能体"""
    
    def __init__(self):
        """初始化 LLM"""
        # TODO: 实现 LLM 初始化
        # self.llm = ChatOpenAI(
        #     model=config.MODEL_NAME,
        #     openai_api_key=config.OPENAI_API_KEY,
        #     openai_api_base=config.OPENAI_BASE_URL,
        #     temperature=0.1  # 低温度保证输出稳定
        # )
        
        self.planning_prompt = self._create_planning_prompt()
    
    def _create_planning_prompt(self) -> ChatPromptTemplate:
        """创建规划提示词模板"""
        template = """你是一位楼宇自控系统的控制逻辑专家。

用户需求：
{user_query}

相关领域知识：
{retrieval_context}

请使用思维链 (Chain of Thought) 方法，将用户需求拆解为清晰的逻辑步骤。

要求：
1. 明确每一步需要的功能块类型
2. 说明数据流向和连接关系
3. 标注关键参数
4. 考虑边界条件和安全保护

输出格式（YAML）：
```yaml
title: <逻辑名称>
steps:
  - step: 1
    description: <步骤描述>
    node_type: <节点类型>
    parameters:
      - name: <参数名>
        value: <参数值>
    inputs: [<上游节点>]
    outputs: [<下游节点>]
```

请开始规划：
"""
        return ChatPromptTemplate.from_template(template)
    
    def plan(self, user_query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成执行计划
        
        Args:
            user_query: 用户需求
            context: 检索到的上下文信息
            
        Returns:
            结构化的执行计划
        """
        # TODO: 调用 LLM 生成规划
        # messages = self.planning_prompt.format_messages(
        #     user_query=user_query,
        #     retrieval_context=str(context)
        # )
        # response = self.llm(messages)
        
        # TODO: 解析 YAML 输出为结构化数据
        
        # 示例计划（硬编码）
        plan = {
            "title": "夏季主机初始开启台数计算",
            "steps": [
                {
                    "step": 1,
                    "description": "读取湿球温度",
                    "node_type": "swInput",
                    "parameters": {
                        "name": "湿球温度",
                        "address": "AI_WetBulb_Temp"
                    },
                    "inputs": [],
                    "outputs": ["compare_nodes"]
                },
                {
                    "step": 2,
                    "description": "定义温度阈值（23°C, 25°C, 27°C, 29°C, 31°C）",
                    "node_type": "constant",
                    "parameters": {
                        "values": [23, 25, 27, 29, 31]
                    },
                    "inputs": [],
                    "outputs": ["compare_nodes"]
                },
                {
                    "step": 3,
                    "description": "温度与阈值比较，每超过一个阈值累加1",
                    "node_type": "compare",
                    "parameters": {
                        "operator": ">",
                        "accumulate": True
                    },
                    "inputs": ["temp_sensor", "thresholds"],
                    "outputs": ["switch_node"]
                },
                {
                    "step": 4,
                    "description": "手自动切换逻辑",
                    "node_type": "switch",
                    "parameters": {
                        "mode_input": "auto_manual_signal"
                    },
                    "inputs": ["compare_result", "manual_override"],
                    "outputs": ["output"]
                }
            ],
            "metadata": {
                "total_nodes": 4,
                "complexity": "medium"
            }
        }
        
        return plan
    
    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        LangGraph 节点调用接口
        
        Args:
            state: 当前工作流状态
            
        Returns:
            更新后的状态
        """
        user_query = state.get("user_query", "")
        context = state.get("retrieval_context", {})
        
        # 生成计划
        plan = self.plan(user_query, context)
        
        # 更新状态
        state["execution_plan"] = plan
        state["current_step"] = "planning_completed"
        
        return state
