"""
LangGraph 工作流编排
定义 6 个智能体的协作流程（DAG + 条件路由）
"""
from typing import TypedDict, Literal
from langgraph.graph import StateGraph, END
from agents.retrieval_agent import RetrievalAgent
from agents.planning_agent import PlanningAgent
from agents.coding_agent import CodingAgent
from agents.validation_agent import ValidationAgent
from agents.debugging_agent import DebuggingAgent
from tools.execution_tool import ExecutionTool
import config


# 定义工作流状态
class WorkflowState(TypedDict):
    """工作流全局状态"""
    user_query: str  # 用户输入的需求
    retrieval_context: dict  # 检索到的上下文
    execution_plan: dict  # 执行计划
    generated_code: str  # 生成的 Python 代码
    execution_result: dict  # 代码执行结果
    validation_result: dict  # 验证结果
    debug_history: list  # 调试历史
    retry_count: int  # 重试次数
    current_step: str  # 当前步骤
    next_step: str  # 下一步骤
    final_output: dict  # 最终输出


def create_workflow() -> StateGraph:
    """
    创建 LangGraph 工作流
    
    Returns:
        配置好的状态图
    """
    # 初始化所有智能体
    retrieval_agent = RetrievalAgent()
    planning_agent = PlanningAgent()
    coding_agent = CodingAgent()
    validation_agent = ValidationAgent()
    debugging_agent = DebuggingAgent()
    execution_tool = ExecutionTool()
    
    # 创建状态图
    workflow = StateGraph(WorkflowState)
    
    # ========== 添加节点 ==========
    workflow.add_node("retrieval", retrieval_agent)
    workflow.add_node("planning", planning_agent)
    workflow.add_node("coding", coding_agent)
    workflow.add_node("execution", execution_tool)
    workflow.add_node("validation", validation_agent)
    workflow.add_node("debugging", debugging_agent)
    
    # ========== 定义边缘（流程）==========
    
    # 1. 开始 -> 检索
    workflow.set_entry_point("retrieval")
    
    # 2. 检索 -> 规划（无条件）
    workflow.add_edge("retrieval", "planning")
    
    # 3. 规划 -> 编码（无条件）
    workflow.add_edge("planning", "coding")
    
    # 4. 编码 -> 执行（无条件）
    workflow.add_edge("coding", "execution")
    
    # 5. 执行 -> 验证 OR 调试（条件边缘）
    def route_after_execution(state: WorkflowState) -> Literal["validation", "debugging"]:
        """根据执行结果决定下一步"""
        if state["execution_result"]["success"]:
            return "validation"
        else:
            return "debugging"
    
    workflow.add_conditional_edges(
        "execution",
        route_after_execution,
        {
            "validation": "validation",
            "debugging": "debugging"
        }
    )
    
    # 6. 验证 -> 结束 OR 调试（条件边缘）
    def route_after_validation(state: WorkflowState) -> Literal["end", "debugging"]:
        """根据验证结果决定是否结束"""
        if state["validation_result"]["passed"]:
            return "end"
        else:
            return "debugging"
    
    workflow.add_conditional_edges(
        "validation",
        route_after_validation,
        {
            "end": END,
            "debugging": "debugging"
        }
    )
    
    # 7. 调试 -> 执行 OR 结束（条件边缘，形成闭环）
    def route_after_debugging(state: WorkflowState) -> Literal["execution", "end"]:
        """根据重试次数决定是否继续"""
        if state["retry_count"] >= config.MAX_RETRY_TIMES:
            # 超过最大重试次数，强制结束
            return "end"
        else:
            # 重新执行修正后的代码
            return "execution"
    
    workflow.add_conditional_edges(
        "debugging",
        route_after_debugging,
        {
            "execution": "execution",
            "end": END
        }
    )
    
    return workflow


def run_workflow(user_query: str) -> dict:
    """
    运行完整工作流
    
    Args:
        user_query: 用户需求描述
        
    Returns:
        最终生成的 JSON 组态
    """
    # 创建工作流
    workflow = create_workflow()
    
    # TODO: 编译图
    # app = workflow.compile()
    
    # 初始化状态
    initial_state = {
        "user_query": user_query,
        "retrieval_context": {},
        "execution_plan": {},
        "generated_code": "",
        "execution_result": {},
        "validation_result": {},
        "debug_history": [],
        "retry_count": 0,
        "current_step": "start",
        "next_step": "",
        "final_output": {}
    }
    
    # TODO: 执行工作流
    # result = app.invoke(initial_state)
    
    # 示例返回（模拟执行）
    result = {
        "success": True,
        "final_output": {
            "version": "1.0",
            "nodes": [],
            "wires": []
        },
        "metadata": {
            "total_steps": 5,
            "retry_count": 0,
            "execution_time": "2.3s"
        }
    }
    
    return result


# 可视化工具（可选）
def visualize_workflow():
    """
    生成工作流的可视化图
    
    TODO: 使用 graphviz 或 mermaid 生成流程图
    返回 Mermaid 格式的字符串
    """
    mermaid_graph = """
graph TD
    Start([开始]) --> Retrieval[检索智能体]
    Retrieval --> Planning[规划智能体]
    Planning --> Coding[编码智能体]
    Coding --> Execution[执行工具]
    
    Execution -->|成功| Validation[验证智能体]
    Execution -->|失败| Debugging[调试智能体]
    
    Validation -->|通过| End([结束])
    Validation -->|未通过| Debugging
    
    Debugging -->|重试次数<3| Execution
    Debugging -->|重试次数>=3| End
    
    style Start fill:#90EE90
    style End fill:#FFB6C1
    style Retrieval fill:#87CEEB
    style Planning fill:#87CEEB
    style Coding fill:#FFD700
    style Execution fill:#DDA0DD
    style Validation fill:#F0E68C
    style Debugging fill:#FFA07A
"""
    return mermaid_graph


if __name__ == "__main__":
    print("=" * 60)
    print("KONG CUBE 智能组态生成系统 - LangGraph 工作流")
    print("=" * 60)
    
    # 测试运行
    test_query = "计算夏季主机初始开启数量，需要手自动切换功能"
    
    print(f"\n用户需求: {test_query}\n")
    
    # TODO: 取消注释以实际运行
    # result = run_workflow(test_query)
    # print(f"生成结果: {result}")
    
    print("\n工作流结构（Mermaid）:")
    print(visualize_workflow())
    
    print("\n注意: 完整运行需要：")
    print("1. 配置 .env 文件中的 API 密钥")
    print("2. 安装所有依赖: pip install -r requirements.txt")
    print("3. 初始化向量数据库: python -m tools.init_vectordb")
    
    # 绘制工作流程图
    print("\n正在生成工作流程图...")
    try:
        workflow = create_workflow()
        app = workflow.compile()  # 必须先编译
        png_data = app.get_graph().draw_mermaid_png()
        with open("workflow_graph2.png", 'wb') as f:
            f.write(png_data)
        print("✅ 流程图已保存为 workflow_graph.png")
    except Exception as e:
        print(f"⚠️  保存图像失败: {e}")
        print("提示: 可能需要安装 pygraphviz 或使用在线 Mermaid 渲染器") 

