"""Standalone LangGraph Send + reducer POC for Phase 7."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Annotated, Any
from pathlib import Path

from typing_extensions import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.phase3_contracts import (
    ParallelMergeConflict,
    SubsystemPlan,
    SubsystemPlanningDispatch,
    empty_parallel_merge_conflicts,
    empty_subsystem_plan,
    merge_parallel_conflicts,
    merge_subsystem_plan_map,
)


class PocParallelState(TypedDict, total=False):
    scenario: str
    dispatch_plan: list[SubsystemPlanningDispatch]
    subsystem_id: str
    dispatch_index: int
    page_id: str
    subsystem_type: str
    worker_mode: str
    signal_name: str
    subsystem_plan_map: Annotated[dict[str, SubsystemPlan], merge_subsystem_plan_map]
    parallel_merge_conflicts: Annotated[list[ParallelMergeConflict], merge_parallel_conflicts]
    ordered_subsystem_ids: list[str]
    merge_summary: dict[str, Any]


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


def _json(data: Any) -> str:
    return json.dumps(_serializable(data), ensure_ascii=False, indent=2)


def _build_dispatch_plan(scenario: str) -> list[SubsystemPlanningDispatch]:
    if scenario == "stable_order":
        return [
            {
                "subsystem_id": "zeta_ctrl",
                "dispatch_index": 1,
                "page_id": "ahu_main",
                "subsystem_type": "fan",
                "worker_mode": "plan",
            },
            {
                "subsystem_id": "beta_ctrl",
                "dispatch_index": 0,
                "page_id": "ahu_main",
                "subsystem_type": "fan",
                "worker_mode": "plan",
            },
            {
                "subsystem_id": "alpha_ctrl",
                "dispatch_index": 1,
                "page_id": "ahu_secondary",
                "subsystem_type": "heater",
                "worker_mode": "plan",
            },
        ]

    if scenario == "conflict_list":
        return [
            {
                "subsystem_id": "supply_fan_ctrl",
                "dispatch_index": 0,
                "page_id": "ahu_main",
                "subsystem_type": "fan",
                "worker_mode": "conflict",
                "signal_name": "shared_supply_cmd",
            },
            {
                "subsystem_id": "heater_ctrl",
                "dispatch_index": 1,
                "page_id": "ahu_main",
                "subsystem_type": "heater",
                "worker_mode": "conflict",
                "signal_name": "shared_supply_cmd",
            },
        ]

    if scenario == "duplicate_subsystem_id":
        return [
            {
                "subsystem_id": "supply_fan_ctrl",
                "dispatch_index": 1,
                "page_id": "ahu_main",
                "subsystem_type": "fan",
                "worker_mode": "plan",
            },
            {
                "subsystem_id": "supply_fan_ctrl",
                "dispatch_index": 0,
                "page_id": "ahu_main",
                "subsystem_type": "fan",
                "worker_mode": "plan",
            },
        ]

    raise ValueError(f"Unsupported scenario: {scenario}")


def prepare_dispatches(state: PocParallelState) -> dict[str, Any]:
    scenario = str(state.get("scenario", "stable_order")).strip() or "stable_order"
    return {"dispatch_plan": _build_dispatch_plan(scenario)}


def dispatch_parallel(state: PocParallelState) -> list[Send]:
    return [Send("subsystem_planning_worker", dispatch) for dispatch in state.get("dispatch_plan", [])]


def _build_subsystem_plan(state: PocParallelState) -> SubsystemPlan:
    subsystem_id = str(state.get("subsystem_id", "")).strip()
    page_id = str(state.get("page_id", "")).strip()
    dispatch_index = int(state.get("dispatch_index", 0))
    subsystem_type = str(state.get("subsystem_type", "generic")).strip() or "generic"

    plan = empty_subsystem_plan(subsystem_id=subsystem_id, page_id=page_id)
    plan.update(
        {
            "dispatch_index": dispatch_index,
            "implementation_mode": "atomic_assembly",
            "selection_reason": "phase7_send_poc_worker_local_update",
            "reasoning": f"worker returns only local state update for {subsystem_id}",
            "node_instances": [
                {
                    "logic_id": f"{subsystem_id}__logic",
                    "module_type": f"{subsystem_type}_module",
                    "page_id": page_id,
                    "template_id": None,
                    "parameters": {"dispatch_index": dispatch_index},
                    "input_count": 1,
                    "output_count": 1,
                    "position": {"x": dispatch_index * 120, "y": 80},
                    "reasoning": "Phase 7 Send POC node",
                }
            ],
        }
    )
    return plan


def _build_parallel_conflict(state: PocParallelState) -> ParallelMergeConflict:
    subsystem_id = str(state.get("subsystem_id", "")).strip()
    signal_name = str(state.get("signal_name", "")).strip()
    dispatch_index = int(state.get("dispatch_index", 0))
    return {
        "type": "parallel_shared_signal_conflict",
        "subsystem_id": subsystem_id,
        "conflicting_subsystem_ids": [subsystem_id],
        "dispatch_index": dispatch_index,
        "signal_name": signal_name,
        "resolution": "reject",
        "message": f"{subsystem_id} exported duplicated shared signal {signal_name}",
    }


def subsystem_planning_worker(state: PocParallelState) -> dict[str, Any]:
    worker_mode = str(state.get("worker_mode", "plan")).strip() or "plan"
    subsystem_id = str(state.get("subsystem_id", "")).strip()

    if worker_mode == "conflict":
        return {
            "parallel_merge_conflicts": [_build_parallel_conflict(state)],
        }

    plan = _build_subsystem_plan(state)
    return {
        "subsystem_plan_map": {subsystem_id: plan},
    }


def subsystem_merge(state: PocParallelState) -> dict[str, Any]:
    subsystem_plan_map = state.get("subsystem_plan_map", {}) or {}
    conflicts = state.get("parallel_merge_conflicts", []) or []
    ordered_subsystem_ids = list(subsystem_plan_map.keys())
    return {
        "ordered_subsystem_ids": ordered_subsystem_ids,
        "merge_summary": {
            "scenario": state.get("scenario", ""),
            "subsystem_count": len(ordered_subsystem_ids),
            "conflict_count": len(conflicts),
            "stable_sort_rule": "dispatch_index -> subsystem_id",
        },
    }


def build_graph():
    builder = StateGraph(PocParallelState)
    builder.add_node("prepare_dispatches", prepare_dispatches)
    builder.add_node("subsystem_planning_worker", subsystem_planning_worker)
    builder.add_node("subsystem_merge", subsystem_merge)
    builder.add_edge(START, "prepare_dispatches")
    builder.add_conditional_edges(
        "prepare_dispatches",
        dispatch_parallel,
        ["subsystem_planning_worker"],
    )
    builder.add_edge("subsystem_planning_worker", "subsystem_merge")
    builder.add_edge("subsystem_merge", END)
    return builder.compile()


def build_initial_state(scenario: str = "stable_order") -> PocParallelState:
    return {
        "scenario": scenario,
        "dispatch_plan": [],
        "subsystem_plan_map": {},
        "parallel_merge_conflicts": empty_parallel_merge_conflicts(),
        "ordered_subsystem_ids": [],
        "merge_summary": {},
    }


def run_poc(scenario: str = "stable_order") -> dict[str, Any]:
    graph = build_graph()
    return graph.invoke(build_initial_state(scenario))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Phase 7 Send + reducer POC.")
    parser.add_argument(
        "--scenario",
        choices=["stable_order", "conflict_list", "duplicate_subsystem_id"],
        default="stable_order",
        help="POC scenario to execute.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("=== Phase 7 Send + reducer POC ===")
    result = run_poc(args.scenario)
    print(_json(result))


if __name__ == "__main__":
    main()
