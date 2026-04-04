"""
LangGraph workflow orchestration.

Phase 1 refactor keeps the workflow linear, but upgrades the middle of the
pipeline from a weak plan -> JSON jump to:

analysis -> retrieval -> planning -> assembly -> coding -> verification -> END
"""
from typing import TypedDict
import os

from langgraph.graph import END, StateGraph
from langsmith import traceable

from agents.analysis_agent import AnalysisAgent
from agents.assembly_agent import AssemblyAgent
from agents.coding_agent import CodingAgent
from agents.planning_agent import PlanningAgent
from agents.verifier_agent import VerifierAgent

try:
    from agents.retrieval_agent import RetrievalAgent
except ModuleNotFoundError:
    RetrievalAgent = None

os.environ["LANGCHAIN_TRACING_V2"] = "false"


class WorkflowState(TypedDict):
    """Shared workflow state."""

    user_query: str
    analysis_result: dict
    retrieval_context: dict
    retrieval_bundle: dict
    execution_plan: dict
    assembled_graph_ir: dict
    compiled_artifact: dict
    verification_report: dict
    generated_code: str
    execution_result: dict
    validation_result: dict
    debug_history: list
    retry_count: int
    current_step: str
    next_step: str
    final_output: dict


@traceable(name="create_workflow", tags=["workflow", "langgraph"])
def create_workflow() -> StateGraph:
    """Create the phase-1 workflow graph."""
    if RetrievalAgent is None:
        raise ImportError("RetrievalAgent 依赖未安装，无法创建正式工作流。")

    analysis_agent = AnalysisAgent()
    retrieval_agent = RetrievalAgent()
    planning_agent = PlanningAgent()
    assembly_agent = AssemblyAgent()
    coding_agent = CodingAgent()
    verifier_agent = VerifierAgent()

    workflow = StateGraph(WorkflowState)

    workflow.add_node("analysis", analysis_agent)
    workflow.add_node("retrieval", retrieval_agent)
    workflow.add_node("planning", planning_agent)
    workflow.add_node("assembly", assembly_agent)
    workflow.add_node("coding", coding_agent)
    workflow.add_node("verification", verifier_agent)

    workflow.set_entry_point("analysis")
    workflow.add_edge("analysis", "retrieval")
    workflow.add_edge("retrieval", "planning")
    workflow.add_edge("planning", "assembly")
    workflow.add_edge("assembly", "coding")
    workflow.add_edge("coding", "verification")
    workflow.add_edge("verification", END)

    return workflow


@traceable(name="run_workflow", tags=["workflow", "langgraph"])
def run_workflow(user_query: str) -> dict:
    """Run the end-to-end workflow and return the final state."""
    workflow = create_workflow()
    app = workflow.compile()

    initial_state = {
        "user_query": user_query,
        "analysis_result": {},
        "retrieval_context": {},
        "retrieval_bundle": {},
        "execution_plan": {},
        "assembled_graph_ir": {},
        "compiled_artifact": {},
        "verification_report": {},
        "generated_code": "",
        "execution_result": {},
        "validation_result": {},
        "debug_history": [],
        "retry_count": 0,
        "current_step": "start",
        "next_step": "",
        "final_output": {},
    }

    invoke_config = {
        "run_name": "MideaWorkflow",
        "tags": ["workflow", "langgraph", "phase1-ir"],
        "metadata": {"user_query": user_query},
    }

    return app.invoke(initial_state, config=invoke_config)


if __name__ == "__main__":
    print("=" * 60)
    print("\n\n测试完整工作流调用:")
    print("=" * 60)

    test_query = "生成一个程序，接收一个输入，输入5v的时候，输出1，输入3v的时候输出2，输入10v的时候输出0"
    print(f"\n用户需求: {test_query}\n")

    result = run_workflow(test_query)

    if result.get("execution_plan"):
        plan = result["execution_plan"]
        print(f"\n{'=' * 60}")
        print("规划输出")
        print("=" * 60)
        print(f"目标: {plan.get('goal', 'N/A')}")
        print(f"节点数: {len(plan.get('nodes', []))}")
        print(f"连接数: {len(plan.get('connections', []))}")

    if result.get("assembled_graph_ir"):
        graph_ir = result["assembled_graph_ir"]
        print(f"\n{'=' * 60}")
        print("Graph IR 输出")
        print("=" * 60)
        print(f"页面数: {len(graph_ir.get('pages', []))}")
        print(f"子流程定义数: {len(graph_ir.get('subflow_definitions', []))}")
        print(f"节点实例数: {len(graph_ir.get('node_instances', []))}")
        print(f"边数: {len(graph_ir.get('edges', []))}")

    if result.get("compiled_artifact"):
        artifact = result["compiled_artifact"]
        report = artifact.get("compile_report", {})
        print(f"\n{'=' * 60}")
        print("编译输出")
        print("=" * 60)
        print(f"JSON 长度: {len(artifact.get('json_text', ''))}")
        print(f"页面数: {report.get('page_count', 0)}")
        print(f"子流程定义数: {report.get('subflow_count', 0)}")
        print(f"节点数: {report.get('node_count', 0)}")

    if result.get("verification_report"):
        verification = result["verification_report"]
        print(f"\n{'=' * 60}")
        print("验收结果")
        print("=" * 60)
        print(f"状态: {verification.get('status', 'unknown')}")
        print(f"错误数: {len(verification.get('issues', []))}")
        print(f"警告数: {len(verification.get('warnings', []))}")

    if result.get("generated_code"):
        json_code = result["generated_code"]
        print(f"\n{'=' * 60}")
        print("JSON 预览")
        print("=" * 60)
        print(json_code[:500])
        if len(json_code) > 500:
            print(f"\n... (总计 {len(json_code)} 字符)")

        from utils.time_utils import generate_output_filename

        output_dir = "generated_flow"
        os.makedirs(output_dir, exist_ok=True)
        output_filename = generate_output_filename(prefix="模块", ext="json")
        output_file = os.path.join(output_dir, output_filename)
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(json_code)

        print(f"\nJSON 已保存到: {os.path.abspath(output_file)}")

    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
