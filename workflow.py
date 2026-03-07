"""
LangGraph 工作流编排
定义 6 个智能体的协作流程（DAG + 条件路由）
"""
from typing import TypedDict
from langgraph.graph import StateGraph, END
from agents.retrieval_agent import RetrievalAgent
from agents.planning_agent import PlanningAgent
from agents.coding_agent import CodingAgent
from langsmith import traceable
import os

os.environ["LANGCHAIN_TRACING_V2"] = "false"

# 定义工作流状态
class WorkflowState(TypedDict):
    """工作流全局状态"""
    user_query: str  # 用户输入的需求
    retrieval_context: dict  # 检索到的完整上下文（原始数据）
    execution_plan: dict  # 执行计划
    generated_code: str  # 生成的 Python 代码
    execution_result: dict  # 代码执行结果
    validation_result: dict  # 验证结果
    debug_history: list  # 调试历史
    retry_count: int  # 重试次数
    current_step: str  # 当前步骤
    next_step: str  # 下一步骤
    final_output: dict  # 最终输出


@traceable(name="create_workflow", tags=["workflow", "langgraph"])
def create_workflow() -> StateGraph:
    """
    创建 LangGraph 工作流
    
    Returns:
        配置好的状态图
    """
    # 初始化所有智能体
    retrieval_agent = RetrievalAgent()
    planning_agent = PlanningAgent()  # 启用规划智能体
    coding_agent = CodingAgent()      # 启用编码智能体
    
    # 创建状态图
    workflow = StateGraph(WorkflowState)
    
    # ========== 添加节点 ==========
    workflow.add_node("retrieval", retrieval_agent)
    workflow.add_node("planning", planning_agent)
    workflow.add_node("coding", coding_agent)
    
    # ========== 定义边缘（流程）==========

    workflow.set_entry_point("retrieval")
    workflow.add_edge("retrieval", "planning")        # 检索 -> 规划
    workflow.add_edge("planning", "coding")           # 规划 -> 编码
    workflow.add_edge("coding", END)                  # 编码 -> 结束（临时）
    
    return workflow


@traceable(name="run_workflow", tags=["workflow", "langgraph"])
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
    app = workflow.compile()
    
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
    invoke_config = {
        "run_name": "MideaWorkflow",
        "tags": ["workflow", "langgraph"],
        "metadata": {"user_query": user_query},
    }

    result = app.invoke(initial_state, config=invoke_config)

    return result



if __name__ == "__main__":
    print("=" * 60)
    # 测试完整工作流
    print("\n\n测试完整工作流调用:")
    print("=" * 60)
    
    test_query = "计算主机负荷，公式为 主机负荷 = 4.18*(冷冻回水温度 - 冷冻供水温度)*冷冻水流量/3.6 。其中 冷冻回水温度、冷冻供水温度、冷冻水流量均为物理输入，主机负荷为物理输出。"
    print(f"\n用户需求: {test_query}\n")
    
    result = run_workflow(test_query)
    
    # 显示原始检索结果
    if result.get("retrieval_context"):
        ctx = result["retrieval_context"]
        print(f"\n📊 检索结果摘要:")
        print(f"  - 查询: {ctx['query']}")
        print(f"  - 找到模块数: {ctx['metadata']['retrieved_count']}")
        print(f"  - 平均置信度: {ctx['metadata']['avg_confidence_score']:.3f}")
        
        if ctx['relevant_nodes']:
            print(f"\n  最相关的模块:")
            for node in ctx['relevant_nodes'][:3]:
                print(f"    • {node['name']} ({node['module_type']}) - {node['similarity_score']:.3f}")
    
    # 显示规划结果
    if result.get("execution_plan"):
        plan = result["execution_plan"]
        print(f"\n\n{'=' * 60}")
        print("🎯 规划智能体输出:")
        print("=" * 60)
        print(f"\n目标: {plan.get('goal', 'N/A')}")
        
        nodes = plan.get('nodes', [])
        if nodes:
            print(f"\n节点列表 ({len(nodes)} 个):")
            for i, node in enumerate(nodes, 1):
                print(f"\n  [{i}] {node.get('logic_id')} ({node.get('module_type')})")
                print(f"      理由: {node.get('reasoning', 'N/A')}")
                if node.get('parameters'):
                    print(f"      参数: {node['parameters']}")
        
        connections = plan.get('connections', [])
        if connections:
            print(f"\n连接关系 ({len(connections)} 条):")
            for conn in connections:
                print(f"  {conn['from_node']}[{conn['from_port_index']}] -> {conn['to_node']}[{conn['to_port_index']}]")
    
    # 显示编码结果
    if result.get("generated_code"):
        print(f"\n\n{'=' * 60}")
        print("🔧 编码智能体输出:")
        print("=" * 60)
        
        json_code = result["generated_code"]
        print(f"\nJSON 文件预览（前 500 字符）:")
        print(json_code[:500])
        if len(json_code) > 500:
            print(f"\n... (总计 {len(json_code)} 字符)")
        
        # 保存到文件
        import os
        from utils.time_utils import generate_output_filename
        
        # 创建输出目录
        output_dir = "generated_flow"
        os.makedirs(output_dir, exist_ok=True)
        
        # 生成带时间戳的文件名
        output_filename = generate_output_filename(prefix="模块", ext="json")
        output_file = os.path.join(output_dir, output_filename)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(json_code)
        
        abs_path = os.path.abspath(output_file)
        print(f"\n✅ JSON 已保存到: {abs_path}")

    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60) 

