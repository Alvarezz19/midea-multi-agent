"""
Trace-enabled workflow entrypoint.

This mirrors the Phase 3 main workflow while recording per-node IO snapshots,
timing, and changed top-level state fields.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, TypedDict
import copy
import json
import os
import time

from langgraph.graph import StateGraph
from langsmith import traceable

from agents.analysis_agent import AnalysisAgent
from agents.architecture_planner import ArchitecturePlanner
from agents.coding_agent import CodingAgent
from agents.global_assembler import GlobalAssembler
from agents.subsystem_planner import SubsystemPlanner
from agents.verifier_agent import VerifierAgent
from workflow import build_initial_state, populate_phase3_workflow

try:
    from agents.retrieval_agent import RetrievalAgent
except ModuleNotFoundError:
    RetrievalAgent = None

os.environ["LANGCHAIN_TRACING_V2"] = "false"


class WorkflowState(TypedDict):
    user_query: str
    analysis_result: dict
    requirement_spec: dict
    retrieval_context: dict
    retrieval_bundle: dict
    decomposition_result: dict
    architecture_plan: dict
    subsystem_plan_map: dict
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


def _make_serializable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {key: _make_serializable(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_make_serializable(item) for item in obj]
    if isinstance(obj, tuple):
        return [_make_serializable(item) for item in obj]
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    return str(obj)


def _truncate_for_display(value: Any, max_len: int = 3000) -> Any:
    if isinstance(value, dict):
        return {key: _truncate_for_display(item, max_len) for key, item in value.items()}
    if isinstance(value, list):
        return [_truncate_for_display(item, max_len) for item in value]
    if isinstance(value, str) and len(value) > max_len:
        return value[:max_len] + f"... (共{len(value)}字符)"
    return value


def _get_changed_fields(before_state: dict, after_state: dict) -> list[str]:
    changed_fields = []
    for key, value in after_state.items():
        if key not in before_state or before_state.get(key) != value:
            changed_fields.append(key)
    return changed_fields


def _wrap_node(node_name: str, node_callable: Callable[[dict], dict], node_io_records: list[dict]) -> Callable[[dict], dict]:
    def wrapped(state: dict) -> dict:
        input_snapshot = _make_serializable(copy.deepcopy(state))
        started_at = datetime.now()
        start_time = time.time()

        try:
            result = node_callable(state)
            output_snapshot = _make_serializable(copy.deepcopy(result))
            status = "success"
        except Exception as exc:
            output_snapshot = {
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
            status = "error"
            raise
        finally:
            elapsed_seconds = round(time.time() - start_time, 2)
            node_io_records.append({
                "node_index": len(node_io_records) + 1,
                "node_name": node_name,
                "status": status,
                "started_at": started_at.strftime("%Y-%m-%d %H:%M:%S"),
                "elapsed_seconds": elapsed_seconds,
                "changed_fields": _get_changed_fields(input_snapshot, output_snapshot) if status == "success" else [],
                "input": input_snapshot,
                "output": output_snapshot,
            })

        return result

    return wrapped


def _save_workflow_trace(user_query: str, node_io_records: list[dict], final_state: dict, total_elapsed_seconds: float) -> dict:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    trace_dir = os.path.join("outputs", f"workflow_trace_{timestamp}")
    os.makedirs(trace_dir, exist_ok=True)

    summary = {
        "execution_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user_query": user_query,
        "total_elapsed_seconds": round(total_elapsed_seconds, 2),
        "node_count": len(node_io_records),
        "nodes": node_io_records,
    }

    summary_json_path = os.path.join(trace_dir, "workflow_node_io_record.json")
    with open(summary_json_path, "w", encoding="utf-8") as file:
        json.dump(summary, file, ensure_ascii=False, indent=2)

    final_state_path = os.path.join(trace_dir, "final_state.json")
    with open(final_state_path, "w", encoding="utf-8") as file:
        json.dump(_make_serializable(final_state), file, ensure_ascii=False, indent=2)

    markdown_lines = [
        "# 工作流节点输入输出记录\n",
        f"**执行时间**: {summary['execution_time']}\n",
        f"**用户需求**: {user_query}\n",
        f"**总耗时**: {summary['total_elapsed_seconds']}s\n",
        f"**节点数量**: {len(node_io_records)}\n",
        f"**运行目录**: {os.path.abspath(trace_dir)}\n",
        "---\n",
    ]

    for record in node_io_records:
        markdown_lines.append(f"## {record['node_index']}. 节点: {record['node_name']}\n")
        markdown_lines.append(f"**状态**: {record['status']}\n")
        markdown_lines.append(f"**开始时间**: {record['started_at']}\n")
        markdown_lines.append(f"**耗时**: {record['elapsed_seconds']}s\n")

        if record["changed_fields"]:
            markdown_lines.append("**变更字段**:\n")
            for field in record["changed_fields"]:
                markdown_lines.append(f"- `{field}`\n")
            markdown_lines.append("\n")

        markdown_lines.append("### 输入\n")
        markdown_lines.append("```json")
        markdown_lines.append(json.dumps(_truncate_for_display(record["input"]), ensure_ascii=False, indent=2))
        markdown_lines.append("```\n")

        markdown_lines.append("### 输出\n")
        markdown_lines.append("```json")
        markdown_lines.append(json.dumps(_truncate_for_display(record["output"]), ensure_ascii=False, indent=2))
        markdown_lines.append("```\n")
        markdown_lines.append("---\n")

    summary_md_path = os.path.join(trace_dir, "workflow_node_io_record.md")
    with open(summary_md_path, "w", encoding="utf-8") as file:
        file.write("\n".join(markdown_lines))

    return {
        "trace_dir": os.path.abspath(trace_dir),
        "summary_json": os.path.abspath(summary_json_path),
        "summary_md": os.path.abspath(summary_md_path),
        "final_state_json": os.path.abspath(final_state_path),
    }


@traceable(name="create_workflow_trace", tags=["workflow", "langgraph", "trace"])
def create_workflow(node_io_records: list[dict] | None = None) -> StateGraph:
    if RetrievalAgent is None:
        raise ImportError("RetrievalAgent 依赖未安装，无法创建正式工作流。")

    analysis_agent = AnalysisAgent()
    retrieval_agent = RetrievalAgent()
    architecture_planner = ArchitecturePlanner()
    subsystem_planner = SubsystemPlanner()
    global_assembler = GlobalAssembler()
    coding_agent = CodingAgent()
    verifier_agent = VerifierAgent()

    if node_io_records is None:
        node_io_records = []

    workflow = StateGraph(WorkflowState)
    return populate_phase3_workflow(
        workflow,
        {
            "analysis": _wrap_node("analysis", analysis_agent, node_io_records),
            "retrieval": _wrap_node("retrieval", retrieval_agent, node_io_records),
            "architecture_planning": _wrap_node("architecture_planning", architecture_planner, node_io_records),
            "subsystem_planning": _wrap_node("subsystem_planning", subsystem_planner, node_io_records),
            "global_assembly": _wrap_node("global_assembly", global_assembler, node_io_records),
            "coding": _wrap_node("coding", coding_agent, node_io_records),
            "verification": _wrap_node("verification", verifier_agent, node_io_records),
        },
    )


@traceable(name="run_workflow_trace", tags=["workflow", "langgraph", "trace"])
def run_workflow(user_query: str) -> dict:
    node_io_records: list[dict] = []
    started_at = time.time()

    workflow = create_workflow(node_io_records=node_io_records)
    app = workflow.compile()

    initial_state = build_initial_state(user_query)

    invoke_config = {
        "run_name": "MideaWorkflowTrace",
        "tags": ["workflow", "langgraph", "phase3-layered-planning", "trace"],
        "metadata": {"user_query": user_query},
    }

    result = None
    try:
        result = app.invoke(initial_state, config=invoke_config)
        return result
    finally:
        final_state = result if result is not None else initial_state
        trace_files = _save_workflow_trace(
            user_query=user_query,
            node_io_records=node_io_records,
            final_state=final_state,
            total_elapsed_seconds=time.time() - started_at,
        )

        if result is not None:
            result.setdefault("final_output", {})
            result["final_output"]["workflow_trace"] = trace_files


if __name__ == "__main__":
    query = "生成一个程序，接收一个输入，输入5v的时候，输出1，输入3v的时候输出2，输入10v的时候输出0"
    result = run_workflow(query)

    print("=" * 60)
    print("Trace workflow completed")
    print("=" * 60)
    print(f"Current step: {result.get('current_step')}")
    if result.get("verification_report"):
        report = result["verification_report"]
        print(f"Verification status: {report.get('status')}")
        print(f"Issues: {len(report.get('issues', []))}")
        print(f"Warnings: {len(report.get('warnings', []))}")
    trace_info = result.get("final_output", {}).get("workflow_trace", {})
    if trace_info:
        print(f"Trace dir: {trace_info.get('trace_dir')}")
