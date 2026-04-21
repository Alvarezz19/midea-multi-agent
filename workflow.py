"""
LangGraph 工作流编排
定义 6 个智能体的协作流程（DAG + 条件路由）
"""
from typing import TypedDict
from langgraph.graph import StateGraph, END
from agents.analysis_agent import AnalysisAgent
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
    analysis_result: dict  # 分析智能体输出
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
    analysis_agent = AnalysisAgent()
    retrieval_agent = RetrievalAgent()
    planning_agent = PlanningAgent()  # 启用规划智能体
    coding_agent = CodingAgent()      # 启用编码智能体
    
    # 创建状态图
    workflow = StateGraph(WorkflowState)
    
    # ========== 添加节点 ==========
    workflow.add_node("analysis", analysis_agent)
    workflow.add_node("retrieval", retrieval_agent)
    workflow.add_node("planning", planning_agent)
    workflow.add_node("coding", coding_agent)
    
    # ========== 定义边缘（流程）==========

    workflow.set_entry_point("analysis")
    workflow.add_edge("analysis", "retrieval")       # 分析 -> 检索
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
        "analysis_result": {},
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
    
    test_query = "生成一个程序，接收一个输入，输入5v的时候，输出1，输入3v的时候输出2，输入10v的时候输出0"
    print(f"\n用户需求: {test_query}\n")
    
    result = run_workflow(test_query)

    # 显示分析结果
    if result.get("analysis_result"):
        analysis = result["analysis_result"]
        retrieval_plan = analysis.get("retrieval_plan", {})
        scenario_analysis = analysis.get("scenario_analysis", {})

        print(f"\n\n{'=' * 60}")
        print("🧠 分析智能体输出:")
        print("=" * 60)

        summary = scenario_analysis.get("summary", "N/A")
        print(f"\n业务摘要: {summary}")

        key_fields = [
            ("business_goal", "业务目标"),
            ("system_type", "系统类型"),
            ("equipment_object", "设备对象"),
            ("actuator", "执行器"),
            ("controlled_variable", "被控量"),
            ("feedback_variable", "反馈量"),
            ("setpoint_variable", "设定值"),
            ("output_signal", "目标输出"),
            ("control_strategy", "控制策略"),
        ]
        for key, label in key_fields:
            value = scenario_analysis.get(key)
            if value:
                print(f"  - {label}: {value}")

        if scenario_analysis.get("ambiguities"):
            print(f"  - 模糊点: {scenario_analysis['ambiguities']}")
        if scenario_analysis.get("assumptions"):
            print(f"  - 假设: {scenario_analysis['assumptions']}")
        if "confidence" in scenario_analysis:
            print(f"  - 置信度: {scenario_analysis.get('confidence', 0):.2f}")

        print(f"\n检索计划:")
        print(f"  - intent: {retrieval_plan.get('intent', 'N/A')}")
        print(f"  - category_l1: {retrieval_plan.get('category_l1', '') or '空'}")
        print(f"  - detected_operations: {retrieval_plan.get('detected_operations', [])}")
        print(f"  - keywords: {retrieval_plan.get('keywords', [])}")
        queries = retrieval_plan.get("queries", [])
        if queries:
            print(f"  - queries ({len(queries)} 条):")
            for i, query in enumerate(queries, 1):
                print(f"    [{i}] {query}")
    
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

