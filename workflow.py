"""
LangGraph workflow orchestration.

The formal workflow keeps the Phase 3 layered-planning backbone, and now
mounts Phase 8 review branches plus the Phase 4 repair loop:

analysis -> ambiguity_router -> retrieval -> architecture_planning
-> architecture_review -> subsystem_planning -> global_assembly
-> coding -> verification -> repair_router -> END/repair_agent
"""
from typing import Any, Callable, TypedDict
import os

from langgraph.graph import END, StateGraph
from langsmith import traceable

from agents.analysis_agent import AnalysisAgent
from agents.ambiguity_router import AmbiguityRouter
from agents.architecture_feedback_apply_agent import ArchitectureFeedbackApplyAgent
from agents.architecture_planner import ArchitecturePlanner
from agents.architecture_review_agent import ArchitectureReviewAgent
from agents.clarification_apply_agent import ClarificationApplyAgent
from agents.clarification_review_agent import ClarificationReviewAgent
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
    ReviewHistoryEntry,
    ReviewRequest,
    ReviewResponse,
    RouteDecision,
    default_retry_budget,
    default_retry_counts_by_scope,
    empty_review_request,
    empty_review_response,
)
from utils.workflow_runtime import build_runtime_invoke_config, compile_state_graph

try:
    from agents.retrieval_agent import RetrievalAgent
except ModuleNotFoundError:
    RetrievalAgent = None

os.environ["LANGCHAIN_TRACING_V2"] = "false"


class WorkflowState(TypedDict):
    """Shared workflow state."""

    user_query: str

    # Formal mainline fields
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

    # Control / reserved fields
    debug_history: list
    repair_context: RepairContext
    repair_history: list[RepairHistoryEntry]
    route_decision: RouteDecision
    retry_count: int
    retry_budget: dict[str, int]
    retry_counts_by_scope: dict[str, int]
    hitl_stage: str
    review_request: ReviewRequest
    review_response: ReviewResponse
    review_history: list[ReviewHistoryEntry]
    review_enabled: bool
    review_required: bool
    review_status: str
    review_id: str
    clarification_round: int
    architecture_feedback_patch: dict
    enable_hitl_clarification: bool
    enable_hitl_architecture_review: bool
    current_step: str


PHASE3_NODE_ORDER = [
    "analysis",
    "retrieval",
    "architecture_planning",
    "subsystem_planning",
    "global_assembly",
    "coding",
    "verification",
]
PHASE8_REVIEW_NODE_ORDER = [
    "ambiguity_router",
    "clarification_review",
    "clarification_apply",
    "architecture_review",
    "architecture_feedback_apply",
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


def get_ambiguity_branch(state: dict[str, Any]) -> str:
    return "clarification_review" if bool((state or {}).get("review_required", False)) else "retrieval"


def get_clarification_review_branch(state: dict[str, Any]) -> str:
    review_required = bool((state or {}).get("review_required", False))
    review_enabled = bool((state or {}).get("review_enabled", False))
    review_status = str((state or {}).get("review_status", "")).strip()
    review_response = (state or {}).get("review_response", {}) or {}
    decision = str(review_response.get("decision", "")).strip()
    if review_required and review_enabled and review_status == "pending":
        return "clarification_review"
    if review_status in {"answered", "applied", "rejected"}:
        return "clarification_apply"
    if decision:
        return "clarification_apply"
    return "retrieval"


def get_clarification_apply_branch(state: dict[str, Any]) -> str:
    decision = str((((state or {}).get("review_response", {}) or {}).get("decision", ""))).strip()
    return "END" if decision == "reject" else "retrieval"


def get_architecture_review_branch(state: dict[str, Any]) -> str:
    review_required = bool((state or {}).get("review_required", False))
    review_enabled = bool((state or {}).get("review_enabled", False))
    review_status = str((state or {}).get("review_status", "")).strip()
    review_response = (state or {}).get("review_response", {}) or {}
    decision = str(review_response.get("decision", "")).strip()
    if review_required and review_enabled and review_status == "pending":
        return "architecture_review"
    if review_status in {"answered", "applied", "rejected"}:
        return "architecture_feedback_apply"
    if decision:
        return "architecture_feedback_apply"
    return "subsystem_planning"


def get_architecture_feedback_apply_branch(state: dict[str, Any]) -> str:
    decision = str((((state or {}).get("review_response", {}) or {}).get("decision", ""))).strip()
    if not decision:
        decision = str((((state or {}).get("architecture_feedback_patch", {}) or {}).get("decision", ""))).strip()
    if decision == "reject":
        return "END"
    if decision in {"feedback", "clarify"}:
        return "architecture_planning"
    return "subsystem_planning"


def _passthrough_node(state: dict[str, Any]) -> dict[str, Any]:
    return state


def populate_phase4_workflow(
    workflow: StateGraph,
    nodes: dict[str, object],
    *,
    enable_repair_loop: bool = False,
) -> StateGraph:
    """Register the shared Phase 4-capable topology."""
    for node_name in PHASE3_NODE_ORDER:
        workflow.add_node(node_name, nodes[node_name])
    for node_name in PHASE8_REVIEW_NODE_ORDER:
        workflow.add_node(node_name, nodes.get(node_name, _passthrough_node))

    if enable_repair_loop:
        missing_nodes = {REPAIR_ROUTER_NODE, REPAIR_AGENT_NODE} - set(nodes)
        if missing_nodes:
            missing = ", ".join(sorted(missing_nodes))
            raise ValueError(f"Phase 4 repair loop requires nodes: {missing}")
        workflow.add_node(REPAIR_ROUTER_NODE, nodes[REPAIR_ROUTER_NODE])
        workflow.add_node(REPAIR_AGENT_NODE, nodes[REPAIR_AGENT_NODE])

    workflow.set_entry_point(PHASE3_NODE_ORDER[0])
    workflow.add_edge("analysis", "ambiguity_router")
    workflow.add_conditional_edges(
        "ambiguity_router",
        get_ambiguity_branch,
        {
            "clarification_review": "clarification_review",
            "retrieval": "retrieval",
        },
    )
    workflow.add_conditional_edges(
        "clarification_review",
        get_clarification_review_branch,
        {
            "clarification_review": "clarification_review",
            "clarification_apply": "clarification_apply",
            "retrieval": "retrieval",
        },
    )
    workflow.add_conditional_edges(
        "clarification_apply",
        get_clarification_apply_branch,
        {
            "retrieval": "retrieval",
            "END": END,
        },
    )
    workflow.add_edge("retrieval", "architecture_planning")
    workflow.add_edge("architecture_planning", "architecture_review")
    workflow.add_conditional_edges(
        "architecture_review",
        get_architecture_review_branch,
        {
            "architecture_review": "architecture_review",
            "architecture_feedback_apply": "architecture_feedback_apply",
            "subsystem_planning": "subsystem_planning",
        },
    )
    workflow.add_conditional_edges(
        "architecture_feedback_apply",
        get_architecture_feedback_apply_branch,
        {
            "architecture_planning": "architecture_planning",
            "subsystem_planning": "subsystem_planning",
            "END": END,
        },
    )
    for source, target in zip(PHASE3_NODE_ORDER[3:], PHASE3_NODE_ORDER[4:]):
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


def build_initial_state(
    user_query: str,
    *,
    enable_hitl_clarification: bool = False,
    enable_hitl_architecture_review: bool = False,
) -> dict:
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
        # Historical / reserved fields
        "debug_history": [],
        "repair_context": {},
        "repair_history": [],
        "route_decision": {},
        "retry_budget": retry_budget,
        "retry_counts_by_scope": retry_counts_by_scope,
        "retry_count": aggregate_retry_count(retry_counts_by_scope),
        "hitl_stage": "none",
        "review_request": empty_review_request(),
        "review_response": empty_review_response(),
        "review_history": [],
        "review_enabled": False,
        "review_required": False,
        "review_status": "none",
        "review_id": "",
        "clarification_round": 0,
        "architecture_feedback_patch": {},
        "enable_hitl_clarification": bool(enable_hitl_clarification),
        "enable_hitl_architecture_review": bool(enable_hitl_architecture_review),
        "current_step": "start",
    }


@traceable(name="create_workflow", tags=["workflow", "langgraph"])
def create_workflow(*, checkpointer: Any | None = None) -> StateGraph:
    """Create the formal workflow graph with review and repair branches."""
    if RetrievalAgent is None:
        raise ImportError("RetrievalAgent 依赖未安装，无法创建正式工作流。")

    analysis_agent = AnalysisAgent()
    ambiguity_router = AmbiguityRouter()
    retrieval_agent = RetrievalAgent()
    clarification_review = ClarificationReviewAgent()
    clarification_apply = ClarificationApplyAgent()
    architecture_planner = ArchitecturePlanner()
    architecture_review = ArchitectureReviewAgent()
    architecture_feedback_apply = ArchitectureFeedbackApplyAgent()
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
            "ambiguity_router": ambiguity_router,
            "clarification_review": clarification_review,
            "clarification_apply": clarification_apply,
            "retrieval": retrieval_agent,
            "architecture_planning": architecture_planner,
            "architecture_review": architecture_review,
            "architecture_feedback_apply": architecture_feedback_apply,
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
def run_workflow(
    user_query: str,
    *,
    thread_id: str | None = None,
    checkpointer: Any | None = None,
    runtime_metadata: dict[str, Any] | None = None,
    enable_hitl_clarification: bool = False,
    enable_hitl_architecture_review: bool = False,
) -> dict:
    """Run the end-to-end workflow and return the final state."""
    workflow = create_workflow(checkpointer=checkpointer)
    app = compile_state_graph(workflow, checkpointer=checkpointer)

    initial_state = build_initial_state(
        user_query,
        enable_hitl_clarification=bool(
            enable_hitl_clarification and checkpointer is not None and str(thread_id or "").strip()
        ),
        enable_hitl_architecture_review=bool(
            enable_hitl_architecture_review and checkpointer is not None and str(thread_id or "").strip()
        ),
    )

    invoke_config = build_runtime_invoke_config(
        user_query=user_query,
        run_name="MideaWorkflow",
        tags=["workflow", "langgraph", "phase3-layered-planning"],
        recursion_limit=PHASE4_RECURSION_LIMIT,
        thread_id=thread_id,
        checkpointer=checkpointer,
        extra_metadata=runtime_metadata,
    )

    return app.invoke(initial_state, config=invoke_config)


if __name__ == "__main__":
    print("=" * 60)
    print("\n\n测试完整工作流调用:")
    print("=" * 60)

    test_query = "生成一个程序，接收一个输入，输入5v的时候，输出1，输入3v的时候输出2，输入10v的时候输出0"
    print(f"\n用户需求: {test_query}\n")

    result = run_workflow(test_query)

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
        json_code = artifact.get("json_text", "")
        print(f"\n{'=' * 60}")
        print("编译输出")
        print("=" * 60)
        print(f"JSON 长度: {len(artifact.get('json_text', ''))}")
        print(f"页面数: {report.get('page_count', 0)}")
        print(f"子流程定义数: {report.get('subflow_count', 0)}")
        print(f"节点数: {report.get('node_count', 0)}")
        if json_code:
            print(f"\n{'=' * 60}")
            print("JSON 预览")
            print("=" * 60)
            print(json_code[:500])
            if len(json_code) > 500:
                print(f"\n... (总计 {len(json_code)} 字符)")

    if result.get("verification_report"):
        verification = result["verification_report"]
        print(f"\n{'=' * 60}")
        print("验收结果")
        print("=" * 60)
        print(f"状态: {verification.get('status', 'unknown')}")
        print(f"错误数: {len(verification.get('issues', []))}")
        print(f"警告数: {len(verification.get('warnings', []))}")

    if result.get("compiled_artifact", {}).get("json_text"):
        json_code = result["compiled_artifact"]["json_text"]
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
