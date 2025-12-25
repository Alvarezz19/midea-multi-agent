"""
编码智能体 (Coding Agent)
职责：将规划方案转化为可执行的 Python 代码（基于 Kong SDK）
"""
from typing import Dict, List, Any
from langchain.chat_models import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
import config


class CodingAgent:
    """编码智能体 - 核心智能体"""
    
    def __init__(self):
        """初始化 LLM"""
        # TODO: 实现 LLM 初始化
        # self.llm = ChatOpenAI(
        #     model=config.MODEL_NAME,
        #     openai_api_key=config.OPENAI_API_KEY,
        #     openai_api_base=config.OPENAI_BASE_URL,
        #     temperature=0  # 零温度保证代码生成的确定性
        # )
        
        self.coding_prompt = self._create_coding_prompt()
    
    def _create_coding_prompt(self) -> ChatPromptTemplate:
        """创建编码提示词模板"""
        template = """你是一位 Python 代码生成专家。请根据规划方案生成基于 Kong SDK 的代码。

执行计划：
{execution_plan}

Kong SDK API 文档：
```python
# 1. 创建流程构建器
flow = FlowBuilder()

# 2. 添加节点
node = flow.add_node(
    node_type="<节点类型>",  # 如 'swInput', 'compare', 'switch'
    name="<节点名称>",
    **params  # 其他参数
)

# 3. 建立连接
source_node.connect(target_node, out_port=0, in_port=0)

# 4. 导出 JSON
json_output = flow.export_json()
```

严格约束：
1. ⚠️ 必须使用 Kong SDK，严禁臆造 API
2. ⚠️ 所有节点类型必须在允许列表中：{allowed_node_types}
3. ⚠️ 代码必须可执行，导入语句完整
4. ⚠️ 使用有意义的变量名

输出格式：
```python
from kong_sdk import FlowBuilder

def generate_flow():
    \"\"\"<功能描述>\"\"\"
    flow = FlowBuilder()
    
    # 步骤1：<描述>
    node1 = flow.add_node(...)
    
    # 步骤2：<描述>
    node2 = flow.add_node(...)
    
    # 建立连接
    node1.connect(node2)
    
    return flow.export_json()

# 生成组态
if __name__ == "__main__":
    result = generate_flow()
    print(result)
```

请开始生成代码：
"""
        return ChatPromptTemplate.from_template(template)
    
    def generate_code(self, plan: Dict[str, Any]) -> str:
        """
        生成 Python 代码
        
        Args:
            plan: 执行计划
            
        Returns:
            Python 代码字符串
        """
        # TODO: 调用 LLM 生成代码
        # allowed_types = list(NODE_TYPES.keys())
        # messages = self.coding_prompt.format_messages(
        #     execution_plan=str(plan),
        #     allowed_node_types=str(allowed_types)
        # )
        # response = self.llm(messages)
        # code = self._extract_code_block(response.content)
        
        # 示例代码（硬编码）
        code = '''from kong_sdk import FlowBuilder

def generate_flow():
    """夏季主机初始开启台数计算逻辑"""
    flow = FlowBuilder()
    
    # 步骤1：读取湿球温度
    temp_sensor = flow.add_node(
        "swInput", 
        "湿球温度",
        address="AI_WetBulb_Temp"
    )
    
    # 步骤2：定义温度阈值
    threshold_23 = flow.add_node("constant", "阈值_23C", value=23.0)
    threshold_25 = flow.add_node("constant", "阈值_25C", value=25.0)
    threshold_27 = flow.add_node("constant", "阈值_27C", value=27.0)
    threshold_29 = flow.add_node("constant", "阈值_29C", value=29.0)
    threshold_31 = flow.add_node("constant", "阈值_31C", value=31.0)
    
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
    
    # TODO: 完整连接其他比较节点
    
    # 步骤4：累加结果
    accumulator = flow.add_node("accumulator", "开机台数")
    compare_1.connect(accumulator)
    compare_2.connect(accumulator)
    # TODO: 连接其他比较结果
    
    # 步骤5：手自动切换
    switch = flow.add_node("switch", "手自动切换")
    accumulator.connect(switch, out_port=0, in_port=0)
    
    return flow.export_json()

if __name__ == "__main__":
    import json
    result = generate_flow()
    print(json.dumps(result, indent=2, ensure_ascii=False))
'''
        return code
    
    def _extract_code_block(self, text: str) -> str:
        """从 Markdown 代码块中提取代码"""
        # TODO: 实现代码提取逻辑
        # 处理 ```python ... ``` 格式
        pass
    
    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        LangGraph 节点调用接口
        
        Args:
            state: 当前工作流状态
            
        Returns:
            更新后的状态
        """
        plan = state.get("execution_plan", {})
        
        # 生成代码
        code = self.generate_code(plan)
        
        # 更新状态
        state["generated_code"] = code
        state["current_step"] = "coding_completed"
        state["retry_count"] = state.get("retry_count", 0)  # 初始化重试计数
        
        return state
