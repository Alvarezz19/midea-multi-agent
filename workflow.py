"""
LangGraph workflow orchestration.

Phase 3 keeps the workflow linear for stability, but upgrades the planning
layer into:

analysis -> retrieval -> architecture_planning -> subsystem_planning
-> global_assembly -> coding -> verification -> END
"""
from typing import Any, TypedDict
import os

from langgraph.graph import END, StateGraph
from langsmith import traceable

from agents.analysis_agent import AnalysisAgent
from agents.architecture_planner import ArchitecturePlanner
from agents.coding_agent import CodingAgent
from agents.global_assembler import GlobalAssembler
from agents.repair_agent import RepairAgent
from agents.repair_router import RepairRouter
from agents.subsystem_planner import SubsystemPlanner
from agents.verifier_agent import VerifierAgent
from utils.phase3_contracts import (
    DEFAULT_RETRY_BUDGET,
    RepairContext,
    RepairHistoryEntry,
    RouteDecision,
    default_retry_budget,
    default_retry_counts_by_scope,
)

try:
    from agents.retrieval_agent import RetrievalAgent
except ModuleNotFoundError:
    RetrievalAgent = None

os.environ["LANGCHAIN_TRACING_V2"] = "false"


class WorkflowState(TypedDict):
    """Shared workflow state."""

    user_query: str

    # Phase 3 formal fields
    analysis_result: dict
    requirement_spec: dict
    retrieval_bundle: dict
    decomposition_result: dict
    architecture_plan: dict
    subsystem_plan_map: dict
    assembled_graph_ir: dict
    compiled_artifact: dict
    verification_report: dict
    final_output: dict

    # Compat fields
    retrieval_context: dict
    execution_plan: dict
    generated_code: str

    # Historical / reserved fields
    execution_result: dict
    validation_result: dict
    debug_history: list
    repair_context: RepairContext
    repair_history: list[RepairHistoryEntry]
    route_decision: RouteDecision
    retry_count: int
    retry_budget: dict[str, int]
    retry_counts_by_scope: dict[str, int]
    current_step: str
    next_step: str


PHASE3_NODE_ORDER = [
    "analysis",
    "retrieval",
    "architecture_planning",
    "subsystem_planning",
    "global_assembly",
    "coding",
    "verification",
]
REPAIR_ROUTER_NODE = "repair_router"
REPAIR_AGENT_NODE = "repair_agent"
PHASE4_RECURSION_LIMIT = 40
PHASE4_REPAIR_DECISION_TO_NEXT: dict[str, str] = {
    "accept": END,
    "planning_repair": REPAIR_AGENT_NODE,
    "assembly_repair": REPAIR_AGENT_NODE,
    "compile_repair": REPAIR_AGENT_NODE,
    "reject": END,
}
PHASE4_RESUME_NODE_TO_NEXT: dict[str, str] = {
    "subsystem_planning": "subsystem_planning",
    "global_assembly": "global_assembly",
    "coding": "coding",
}
PHASE4_REPAIR_AGENT_DECISION_TO_NEXT: dict[str, str] = {
    "subsystem_planning": "subsystem_planning",
    "global_assembly": "global_assembly",
    "coding": "coding",
    "END": END,
}


def _coerce_non_negative_int(value: Any, default: int = 0) -> int:
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return default


def normalize_retry_budget(retry_budget: dict[str, Any] | None) -> dict[str, int]:
    normalized = default_retry_budget()
    for scope in DEFAULT_RETRY_BUDGET:
        if retry_budget is None:
            continue
        normalized[scope] = _coerce_non_negative_int(retry_budget.get(scope), normalized[scope])
    return normalized


def normalize_retry_counts_by_scope(retry_counts_by_scope: dict[str, Any] | None) -> dict[str, int]:
    normalized = default_retry_counts_by_scope()
    for scope in normalized:
        if retry_counts_by_scope is None:
            continue
        normalized[scope] = _coerce_non_negative_int(retry_counts_by_scope.get(scope), 0)
    return normalized


def aggregate_retry_count(retry_counts_by_scope: dict[str, Any] | None) -> int:
    return sum(normalize_retry_counts_by_scope(retry_counts_by_scope).values())


def get_repair_router_branch(state: dict[str, Any]) -> str:
    decision = str(((state or {}).get("route_decision", {}) or {}).get("decision", "")).strip()
    return decision if decision in PHASE4_REPAIR_DECISION_TO_NEXT else "reject"


def get_repair_resume_branch(state: dict[str, Any]) -> str:
    resume_node = str(((state or {}).get("repair_context", {}) or {}).get("resume_node", "")).strip()
    if resume_node not in PHASE4_RESUME_NODE_TO_NEXT:
        raise ValueError(f"Unsupported repair resume node: {resume_node or '<empty>'}")
    return resume_node


def get_repair_agent_branch(state: dict[str, Any]) -> str:
    decision = str(((state or {}).get("route_decision", {}) or {}).get("decision", "")).strip()
    if decision == "reject":
        return "END"
    return get_repair_resume_branch(state)


def populate_phase3_workflow(workflow: StateGraph, nodes: dict[str, object]) -> StateGraph:
    """Register the shared Phase 3 linear topology."""
    return populate_phase4_workflow(workflow, nodes, enable_repair_loop=False)


def populate_phase4_workflow(
    workflow: StateGraph,
    nodes: dict[str, object],
    *,
    enable_repair_loop: bool = False,
) -> StateGraph:
    """Register the shared Phase 4-capable topology."""
    for node_name in PHASE3_NODE_ORDER:
        workflow.add_node(node_name, nodes[node_name])

    if enable_repair_loop:
        missing_nodes = {REPAIR_ROUTER_NODE, REPAIR_AGENT_NODE} - set(nodes)
        if missing_nodes:
            missing = ", ".join(sorted(missing_nodes))
            raise ValueError(f"Phase 4 repair loop requires nodes: {missing}")
        workflow.add_node(REPAIR_ROUTER_NODE, nodes[REPAIR_ROUTER_NODE])
        workflow.add_node(REPAIR_AGENT_NODE, nodes[REPAIR_AGENT_NODE])

    workflow.set_entry_point(PHASE3_NODE_ORDER[0])
    for source, target in zip(PHASE3_NODE_ORDER, PHASE3_NODE_ORDER[1:]):
        workflow.add_edge(source, target)

    if enable_repair_loop:
        workflow.add_edge(PHASE3_NODE_ORDER[-1], REPAIR_ROUTER_NODE)
        workflow.add_conditional_edges(
            REPAIR_ROUTER_NODE,
            get_repair_router_branch,
            PHASE4_REPAIR_DECISION_TO_NEXT,
        )
        workflow.add_conditional_edges(
            REPAIR_AGENT_NODE,
            get_repair_agent_branch,
            PHASE4_REPAIR_AGENT_DECISION_TO_NEXT,
        )
    else:
        workflow.add_edge(PHASE3_NODE_ORDER[-1], END)
    return workflow


def build_initial_state(user_query: str) -> dict:
    """Create the canonical initial state shared by both entrypoints."""
    retry_budget = default_retry_budget()
    retry_counts_by_scope = default_retry_counts_by_scope()
    return {
        "user_query": user_query,
        # Phase 3 formal fields
        "analysis_result": {},
        "requirement_spec": {},
        "retrieval_bundle": {},
        "decomposition_result": {},
        "architecture_plan": {},
        "subsystem_plan_map": {},
        "assembled_graph_ir": {},
        "compiled_artifact": {},
        "verification_report": {},
        "final_output": {},
        # Compat fields
        "retrieval_context": {},
        "execution_plan": {},
        "generated_code": "",
        # Historical / reserved fields
        "execution_result": {},
        "validation_result": {},
        "debug_history": [],
        "repair_context": {},
        "repair_history": [],
        "route_decision": {},
        "retry_budget": retry_budget,
        "retry_counts_by_scope": retry_counts_by_scope,
        "retry_count": aggregate_retry_count(retry_counts_by_scope),
        "current_step": "start",
        "next_step": "",
    }


@traceable(name="create_workflow", tags=["workflow", "langgraph"])
def create_workflow() -> StateGraph:
    """Create the Phase 4 workflow graph."""
    if RetrievalAgent is None:
        raise ImportError("RetrievalAgent 依赖未安装，无法创建正式工作流。")

    analysis_agent = AnalysisAgent()
    retrieval_agent = RetrievalAgent()
    architecture_planner = ArchitecturePlanner()
    subsystem_planner = SubsystemPlanner()
    global_assembler = GlobalAssembler()
    coding_agent = CodingAgent()
    verifier_agent = VerifierAgent()
    repair_router = RepairRouter()
    repair_agent = RepairAgent()

    workflow = StateGraph(WorkflowState)
    return populate_phase4_workflow(
        workflow,
        {
            "analysis": analysis_agent,
            "retrieval": retrieval_agent,
            "architecture_planning": architecture_planner,
            "subsystem_planning": subsystem_planner,
            "global_assembly": global_assembler,
            "coding": coding_agent,
            "verification": verifier_agent,
            "repair_router": repair_router,
            "repair_agent": repair_agent,
        },
        enable_repair_loop=True,
    )


@traceable(name="run_workflow", tags=["workflow", "langgraph"])
def run_workflow(user_query: str) -> dict:
    """Run the end-to-end workflow and return the final state."""
    workflow = create_workflow()
    app = workflow.compile()

    initial_state = build_initial_state(user_query)

    invoke_config = {
        "run_name": "MideaWorkflow",
        "tags": ["workflow", "langgraph", "phase3-layered-planning"],
        "metadata": {"user_query": user_query},
        "recursion_limit": PHASE4_RECURSION_LIMIT,
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
