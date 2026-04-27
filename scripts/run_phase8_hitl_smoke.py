"""Phase 8 HITL / persistence smoke for clarification and architecture review."""
from __future__ import annotations

import argparse
import json
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph
from langgraph.types import Command

import workflow
from agents.ambiguity_router import AmbiguityRouter
from agents.architecture_feedback_apply_agent import ArchitectureFeedbackApplyAgent
from agents.architecture_review_agent import ArchitectureReviewAgent
from agents.clarification_apply_agent import ClarificationApplyAgent
from agents.clarification_review_agent import ClarificationReviewAgent
from utils.workflow_runtime import build_configurable_thread


def _json(data: Any) -> str:
    return json.dumps(_serializable(data), ensure_ascii=False, indent=2)


def _serializable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _serializable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serializable(item) for item in value]
    if isinstance(value, tuple):
        return [_serializable(item) for item in value]
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    if hasattr(value, "__dict__"):
        return _serializable(vars(value))
    return str(value)


def _snapshot_to_dict(snapshot: Any) -> dict[str, Any]:
    return {
        "next": list(getattr(snapshot, "next", ()) or ()),
        "values": getattr(snapshot, "values", {}),
        "config": getattr(snapshot, "config", {}),
        "metadata": getattr(snapshot, "metadata", {}),
    }


class _SmokeAnalysis:
    def __init__(self, mode: str) -> None:
        self.mode = mode

    def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        if self.mode == "clarification":
            state["analysis_result"] = {
                "scenario_analysis": {
                    "summary": "控制程序",
                    "system_type": "",
                    "input_signals": [],
                    "output_signals": [],
                    "ambiguities": ["系统类型未明确"],
                    "assumptions": [],
                    "confidence": 0.2,
                },
                "clarification_signals": {
                    "should_clarify": True,
                    "signals": [
                        {"code": "missing_system_type", "severity": "high", "message": "系统类型未明确。"},
                        {"code": "missing_key_subsystems", "severity": "high", "message": "未识别出稳定的子系统边界。"},
                    ],
                    "signal_count": 2,
                },
            }
            state["requirement_spec"] = {
                "schema_version": "3.0",
                "system_type": "",
                "scenario_summary": "控制程序",
                "subsystems": [],
                "signals": {"inputs": [], "outputs": [], "software_points": [], "alarm_points": []},
                "required_pages": [],
                "global_modes": [],
                "ambiguities": ["系统类型未明确"],
                "assumptions": [],
                "acceptance_criteria": [],
                "confidence": 0.2,
                "warnings": ["未能从场景分析中识别系统类型。"],
            }
        else:
            state["analysis_result"] = {
                "scenario_analysis": {
                    "summary": "AHU 系统骨架",
                    "system_type": "AHU",
                    "input_signals": ["送风温度"],
                    "output_signals": ["送风机启停命令"],
                    "ambiguities": [],
                    "assumptions": [],
                    "confidence": 0.9,
                },
                "clarification_signals": {
                    "should_clarify": False,
                    "signals": [],
                    "signal_count": 0,
                },
            }
            state["requirement_spec"] = {
                "schema_version": "3.0",
                "system_type": "AHU",
                "scenario_summary": "AHU 系统骨架",
                "subsystems": [
                    {
                        "subsystem_id": "supply_fan_ctrl",
                        "subsystem_type": "supply_fan_control",
                        "goal": "送风机控制",
                        "page_hint": "控制",
                        "priority": 1,
                        "preferred_templates": [],
                        "imports": ["schedule_enable"],
                        "exports": ["supply_fan_available_flag"],
                    }
                ],
                "signals": {
                    "inputs": ["送风温度"],
                    "outputs": ["送风机启停命令"],
                    "software_points": [],
                    "alarm_points": [],
                },
                "required_pages": ["控制"],
                "global_modes": [],
                "ambiguities": [],
                "assumptions": [],
                "acceptance_criteria": [],
                "confidence": 0.9,
                "warnings": [],
            }
        state["current_step"] = "analysis_completed"
        return state


class _SmokeRetrieval:
    def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        state["retrieval_bundle"] = {"source": "phase8-smoke"}
        state["retrieval_context"] = {"source": "phase8-smoke"}
        state["current_step"] = "retrieval_completed"
        return state


class _SmokeArchitecturePlanning:
    def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        history = list(state.get("debug_history", []) or [])
        patch = state.get("architecture_feedback_patch", {}) or {}
        patch_decision = str(patch.get("decision", "") or "").strip()
        if patch_decision in {"feedback", "clarify"}:
            history.append("architecture_run_2")
            page_labels = ["控制", "总览"]
            constraint = {"summary": "补充总览页约束"}
        else:
            history.append("architecture_run_1")
            page_labels = ["控制"]
            constraint = {"summary": "保持控制页为主"}

        state["debug_history"] = history
        state["decomposition_result"] = {
            "pages": [{"page_id": label, "label": label} for label in page_labels],
            "subsystem_descriptors": [
                {
                    "subsystem_id": "supply_fan_ctrl",
                    "imports": ["schedule_enable"],
                    "exports": ["supply_fan_available_flag"],
                }
            ],
            "shared_signal_registry": [
                {
                    "signal_name": "supply_fan_available_flag",
                    "signal_key": "supply_fan_available_flag",
                    "owner_subsystem_id": "supply_fan_ctrl",
                    "consumers": [],
                }
            ],
            "template_needs": [],
            "planning_order": ["supply_fan_ctrl"],
            "warnings": [],
        }
        state["architecture_plan"] = {
            "goal": "phase8-smoke-architecture",
            "pages": [{"page_id": label, "label": label} for label in page_labels],
            "subsystem_slots": [{"subsystem_id": "supply_fan_ctrl", "page_id": "控制"}],
            "shared_signal_registry": [
                {
                    "signal_name": "supply_fan_available_flag",
                    "signal_key": "supply_fan_available_flag",
                    "owner_subsystem_id": "supply_fan_ctrl",
                    "consumers": [],
                }
            ],
            "global_constraints": [constraint],
            "naming_strategy": {},
            "layout_strategy": {},
            "pattern_bindings": [],
            "warnings": [],
        }
        state["current_step"] = "architecture_planned"
        return state


class _SmokeSubsystemPlanning:
    def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        state["subsystem_plan_map"] = {"supply_fan_ctrl": {"status": "planned"}}
        state["current_step"] = "subsystem_planned"
        return state


class _SmokeAssembly:
    def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        state["assembled_graph_ir"] = {"unresolved_items": []}
        state["execution_plan"] = {"goal": "phase8-smoke"}
        state["current_step"] = "global_assembly_completed"
        return state


class _SmokeCoding:
    def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        state["compiled_artifact"] = {"compile_report": {"page_count": 0, "subflow_count": 0, "node_count": 0}}
        state["generated_code"] = "{}"
        state["current_step"] = "coding_completed"
        return state


class _SmokeVerification:
    def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        state["verification_report"] = {
            "status": "passed",
            "repair_scope": "none",
            "issue_summary": "ok",
            "issues": [],
            "warnings": [],
            "metrics": {},
        }
        state["final_output"] = {"status": "ok"}
        state["current_step"] = "verification_completed"
        return state


class _SmokeRepairRouter:
    def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        state["route_decision"] = {
            "decision": "accept",
            "repair_scope": "none",
            "next_node": "END",
            "reason": "verification_passed",
            "issue_ids": [],
            "retry_exhausted": False,
            "retry_count_for_scope": 0,
            "retry_budget_for_scope": 2,
        }
        return state


class _SmokeRepairAgent:
    def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        return state


def build_smoke_graph(mode: str):
    nodes = {
        "analysis": _SmokeAnalysis(mode),
        "ambiguity_router": AmbiguityRouter(),
        "clarification_review": ClarificationReviewAgent(),
        "clarification_apply": ClarificationApplyAgent(),
        "retrieval": _SmokeRetrieval(),
        "architecture_planning": _SmokeArchitecturePlanning(),
        "architecture_review": ArchitectureReviewAgent(),
        "architecture_feedback_apply": ArchitectureFeedbackApplyAgent(),
        "subsystem_planning": _SmokeSubsystemPlanning(),
        "global_assembly": _SmokeAssembly(),
        "coding": _SmokeCoding(),
        "verification": _SmokeVerification(),
        "repair_router": _SmokeRepairRouter(),
        "repair_agent": _SmokeRepairAgent(),
    }
    return workflow.populate_phase4_workflow(
        StateGraph(workflow.WorkflowState),
        nodes,
        enable_repair_loop=True,
    ).compile(checkpointer=InMemorySaver())


def build_smoke_initial_state(mode: str) -> dict[str, Any]:
    if mode == "clarification":
        return workflow.build_initial_state("请生成一个控制程序", enable_hitl_clarification=True)
    return workflow.build_initial_state("请为 AHU 生成系统骨架", enable_hitl_architecture_review=True)


def build_resume_payload(mode: str, resume: str, review_id: str) -> dict[str, Any]:
    if mode == "clarification":
        if resume == "approve":
            return {
                "decision": "approve",
                "answers": ["沿用当前保守假设"],
                "feedback": "",
                "updated_constraints": {},
                "review_id": review_id,
            }
        if resume == "clarify":
            return {
                "decision": "clarify",
                "answers": ["系统类型为 AHU", "必须包含控制页和定时页"],
                "feedback": "按 AHU 标准控制继续。",
                "updated_constraints": {
                    "system_type": "AHU",
                    "required_pages": ["控制", "定时"],
                    "assumptions": ["按 AHU 标准控制继续。"],
                },
                "review_id": review_id,
            }
        return {
            "decision": "reject",
            "answers": [],
            "feedback": "终止本轮。",
            "updated_constraints": {},
            "review_id": review_id,
        }

    if resume == "feedback":
        return {
            "decision": "feedback",
            "answers": ["请增加总览页"],
            "feedback": "结构上需要在子系统规划前补一个总览页。",
            "updated_constraints": {
                "required_pages": ["控制", "总览"],
                "assumptions": ["增加总览页后再进入子系统规划。"],
            },
            "review_id": review_id,
        }
    if resume == "reject":
        return {
            "decision": "reject",
            "answers": [],
            "feedback": "终止本轮。",
            "updated_constraints": {},
            "review_id": review_id,
        }
    return {
        "decision": "approve",
        "answers": [],
        "feedback": "",
        "updated_constraints": {},
        "review_id": review_id,
    }


def run_smoke(thread_id: str, mode: str, resume: str) -> None:
    graph = build_smoke_graph(mode)
    config = {"configurable": build_configurable_thread(thread_id)}
    initial_state = build_smoke_initial_state(mode)

    print("=== First invoke: expect interrupt ===")
    first_result = graph.invoke(initial_state, config)
    print(_json(first_result))

    paused_state = graph.get_state(config)
    print("=== Paused state via get_state ===")
    print(_json(_snapshot_to_dict(paused_state)))

    review_id = str(paused_state.values.get("review_id", "") or "").strip()
    resume_payload = build_resume_payload(mode, resume, review_id)

    print("=== Resume with Command ===")
    second_result = graph.invoke(Command(resume=resume_payload), config)
    print(_json(second_result))

    latest_state = graph.get_state(config)
    print("=== Latest state via get_state ===")
    print(_json(_snapshot_to_dict(latest_state)))

    history = list(graph.get_state_history(config))
    print("=== State history via get_state_history ===")
    print(_json([_snapshot_to_dict(snapshot) for snapshot in history[:5]]))

    if mode == "architecture" and resume == "feedback" and "__interrupt__" in second_result:
        followup_review_id = str(latest_state.values.get("review_id", "") or "").strip()
        print("=== Resume follow-up architecture review with approve ===")
        final_result = graph.invoke(
            Command(
                resume={
                    "decision": "approve",
                    "answers": [],
                    "feedback": "",
                    "updated_constraints": {},
                    "review_id": followup_review_id,
                }
            ),
            config,
        )
        print(_json(final_result))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Phase 8 HITL / persistence smoke.")
    parser.add_argument("--thread-id", required=True, help="Thread id used by the checkpointer.")
    parser.add_argument(
        "--mode",
        choices=["clarification", "architecture"],
        required=True,
        help="Which review stage to smoke.",
    )
    parser.add_argument(
        "--resume",
        choices=["approve", "feedback", "reject", "clarify"],
        default="approve",
        help="How to resume the first interrupt.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_smoke(thread_id=args.thread_id, mode=args.mode, resume=args.resume)


if __name__ == "__main__":
    main()
