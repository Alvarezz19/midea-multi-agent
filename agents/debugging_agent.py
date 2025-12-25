"""
调试智能体 (Debugging Agent)
职责：故障修复，分析错误并生成修正代码
"""
from typing import Dict, List, Any
from langchain.chat_models import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
import config


class DebuggingAgent:
    """调试智能体"""
    
    def __init__(self):
        """初始化 LLM"""
        # TODO: 实现 LLM 初始化
        # self.llm = ChatOpenAI(
        #     model=config.MODEL_NAME,
        #     openai_api_key=config.OPENAI_API_KEY,
        #     openai_api_base=config.OPENAI_BASE_URL,
        #     temperature=0.1
        # )
        
        self.debug_prompt = self._create_debug_prompt()
    
    def _create_debug_prompt(self) -> ChatPromptTemplate:
        """创建调试提示词"""
        template = """你是一位 Python 调试专家和楼宇自控系统工程师。

原始代码：
```python
{original_code}
```

错误信息：
{error_info}

验证报告（如有）：
{validation_report}

请分析错误原因并生成修正后的代码。

分析要求：
1. 识别错误类型（语法错误/运行时错误/逻辑错误）
2. 定位错误根源
3. 提供修复方案

约束：
- 必须保持使用 Kong SDK
- 不得改变核心逻辑意图
- 修复后的代码必须可执行

输出格式（JSON）：
{{
    "error_analysis": {{
        "type": "syntax/runtime/logic/validation",
        "root_cause": "错误根源描述",
        "affected_lines": [行号列表]
    }},
    "fix_strategy": "修复策略说明",
    "revised_code": "修正后的完整 Python 代码"
}}

请开始调试：
"""
        return ChatPromptTemplate.from_template(template)
    
    def analyze_error(self, code: str, error: str, validation_report: Dict = None) -> Dict[str, Any]:
        """
        分析错误并生成修复
        
        Args:
            code: 原始代码
            error: 错误信息（Traceback 或验证错误）
            validation_report: 验证报告（可选）
            
        Returns:
            修复方案
        """
        # TODO: 调用 LLM 进行错误分析
        # messages = self.debug_prompt.format_messages(
        #     original_code=code,
        #     error_info=error,
        #     validation_report=str(validation_report) if validation_report else "无"
        # )
        # response = self.llm(messages)
        # fix = json.loads(response.content)
        
        # 示例修复（硬编码）
        fix = {
            "error_analysis": {
                "type": "runtime",
                "root_cause": "调用了不存在的节点类型 'constant'，应使用 'math' 节点",
                "affected_lines": [15, 16, 17]
            },
            "fix_strategy": "将 'constant' 节点替换为 'math' 节点，使用固定值模式",
            "revised_code": '''from kong_sdk import FlowBuilder

def generate_flow():
    """夏季主机初始开启台数计算逻辑（修正版）"""
    flow = FlowBuilder()
    
    # 步骤1：读取湿球温度
    temp_sensor = flow.add_node(
        "swInput", 
        "湿球温度",
        address="AI_WetBulb_Temp"
    )
    
    # 步骤2：定义温度阈值（修正：使用 math 节点）
    threshold_23 = flow.add_node("math", "阈值_23C", operation="const", value=23.0)
    threshold_25 = flow.add_node("math", "阈值_25C", operation="const", value=25.0)
    threshold_27 = flow.add_node("math", "阈值_27C", operation="const", value=27.0)
    threshold_29 = flow.add_node("math", "阈值_29C", operation="const", value=29.0)
    threshold_31 = flow.add_node("math", "阈值_31C", operation="const", value=31.0)
    
    # 步骤3：温度比较
    compare_1 = flow.add_node("compare", "比较_23", operator=">")
    compare_2 = flow.add_node("compare", "比较_25", operator=">")
    compare_3 = flow.add_node("compare", "比较_27", operator=">")
    compare_4 = flow.add_node("compare", "比较_29", operator=">")
    compare_5 = flow.add_node("compare", "比较_31", operator=">")
    
    # 建立比较连接
    temp_sensor.connect(compare_1, out_port=0, in_port=0)
    threshold_23.connect(compare_1, out_port=0, in_port=1)
    
    temp_sensor.connect(compare_2, out_port=0, in_port=0)
    threshold_25.connect(compare_2, out_port=0, in_port=1)
    
    temp_sensor.connect(compare_3, out_port=0, in_port=0)
    threshold_27.connect(compare_3, out_port=0, in_port=1)
    
    # 步骤4：累加结果
    accumulator = flow.add_node("accumulator", "开机台数")
    compare_1.connect(accumulator)
    compare_2.connect(accumulator)
    compare_3.connect(accumulator)
    
    # 步骤5：手自动切换
    switch = flow.add_node("switch", "手自动切换")
    accumulator.connect(switch, out_port=0, in_port=0)
    
    return flow.export_json()

if __name__ == "__main__":
    import json
    result = generate_flow()
    print(json.dumps(result, indent=2, ensure_ascii=False))
'''
        }
        
        return fix
    
    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        LangGraph 节点调用接口
        
        Args:
            state: 当前工作流状态
            
        Returns:
            更新后的状态
        """
        original_code = state.get("generated_code", "")
        execution_result = state.get("execution_result", {})
        validation_result = state.get("validation_result", {})
        
        # 提取错误信息
        error_info = execution_result.get("error", "") or \
                     str(validation_result.get("formal_validation", {}).get("errors", []))
        
        # 执行调试
        fix = self.analyze_error(original_code, error_info, validation_result)
        
        # 更新状态
        state["generated_code"] = fix["revised_code"]  # 替换为修正后的代码
        state["debug_history"] = state.get("debug_history", [])
        state["debug_history"].append({
            "iteration": len(state["debug_history"]) + 1,
            "error": error_info,
            "fix_strategy": fix["fix_strategy"]
        })
        state["retry_count"] = state.get("retry_count", 0) + 1
        state["current_step"] = "debugging_completed"
        
        # 检查是否超过最大重试次数
        if state["retry_count"] >= config.MAX_RETRY_TIMES:
            state["current_step"] = "max_retries_reached"
        
        return state
