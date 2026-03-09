"""
LangGraph 工作流编排
定义 6 个智能体的协作流程（DAG + 条件路由）
"""
from typing import TypedDict, Any, Callable
import copy
import json
import time
from datetime import datetime
from langgraph.graph import StateGraph, END
from agents.retrieval_agent import RetrievalAgent
from agents.planning_agent import PlanningAgent
from agents.coding_agent import CodingAgent
from agents.validation_agent import ValidationAgent
from agents.debugging_agent import DebuggingAgent
from tools.execution_tool import ExecutionTool
import config
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


def _make_serializable(obj: Any) -> Any:
    """将任意对象转换为可 JSON 序列化的结构。"""
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
    """递归截断过长文本，便于 Markdown 展示。"""
    if isinstance(value, dict):
        return {key: _truncate_for_display(item, max_len) for key, item in value.items()}
    if isinstance(value, list):
        return [_truncate_for_display(item, max_len) for item in value]
    if isinstance(value, str) and len(value) > max_len:
        return value[:max_len] + f"... (共{len(value)}字符)"
    return value


def _get_changed_fields(before_state: dict, after_state: dict) -> list[str]:
    """返回顶层发生变化的字段列表，便于快速定位节点产出。"""
    changed_fields = []
    for key, value in after_state.items():
        if key not in before_state or before_state.get(key) != value:
            changed_fields.append(key)
    return changed_fields


def _wrap_node(node_name: str, node_callable: Callable[[dict], dict], node_io_records: list[dict]) -> Callable[[dict], dict]:
    """包装 LangGraph 节点，记录输入、输出、耗时和异常。"""
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
    """保存节点输入输出记录到 outputs 目录。"""
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

        markdown_lines.append("### 输入 (Input)\n")
        markdown_lines.append("```json")
        markdown_lines.append(json.dumps(_truncate_for_display(record["input"]), ensure_ascii=False, indent=2))
        markdown_lines.append("```\n")

        markdown_lines.append("### 输出 (Output)\n")
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


@traceable(name="create_workflow", tags=["workflow", "langgraph"])
def create_workflow(node_io_records: list[dict] | None = None) -> StateGraph:
    """
    创建 LangGraph 工作流
    
    Returns:
        配置好的状态图
    """
    # 初始化所有智能体
    retrieval_agent = RetrievalAgent()
    planning_agent = PlanningAgent()  # 启用规划智能体
    coding_agent = CodingAgent()      # 启用编码智能体
    # validation_agent = ValidationAgent()
    # debugging_agent = DebuggingAgent()
    # execution_tool = ExecutionTool()

    if node_io_records is None:
        node_io_records = []
    
    # 创建状态图
    workflow = StateGraph(WorkflowState)
    
    # ========== 添加节点 ==========
    workflow.add_node("retrieval", _wrap_node("retrieval", retrieval_agent, node_io_records))
    workflow.add_node("planning", _wrap_node("planning", planning_agent, node_io_records))  # 启用规划节点
    workflow.add_node("coding", _wrap_node("coding", coding_agent, node_io_records))     # 启用编码节点
    # workflow.add_node("execution", execution_tool)
    # workflow.add_node("validation", validation_agent)
    # workflow.add_node("debugging", debugging_agent)
    
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
    node_io_records: list[dict] = []

    # 创建工作流
    workflow = create_workflow(node_io_records=node_io_records)
    
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

    total_start_time = time.time()
    result = None
    try:
        result = app.invoke(initial_state, config=invoke_config)
    finally:
        total_elapsed_seconds = time.time() - total_start_time
        final_state = result if result is not None else initial_state
        trace_files = _save_workflow_trace(
            user_query=user_query,
            node_io_records=node_io_records,
            final_state=final_state,
            total_elapsed_seconds=total_elapsed_seconds,
        )

        if result is not None:
            result.setdefault("final_output", {})
            result["final_output"]["workflow_trace"] = trace_files

    return result



if __name__ == "__main__":
    print("=" * 60)
    # 测试完整工作流
    print("\n\n测试完整工作流调用:")
    print("=" * 60)
    
    test_query = "计算主机负荷，公式为 主机负荷 = 4.18*(冷冻回水温度 - 冷冻供水温度)*冷冻水流量/3.6 。其中 冷冻回水温度、冷冻供水温度、冷冻水流量均为物理输入，主机负荷为物理输出。"
    print(f"\n用户需求: {test_query}\n")
    
    result = run_workflow(test_query)

    trace_info = result.get("final_output", {}).get("workflow_trace", {})
    if trace_info:
        print(f"\n📝 节点输入输出记录已保存到: {trace_info['trace_dir']}")
    
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

    # 保存工作流完整输出到 outputs 目录
    # outputs_dir = "outputs"
