"""Standalone LangGraph HITL / persistence POC for Phase 4."""
from __future__ import annotations

import argparse
import json
from typing import Any

from typing_extensions import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from utils.workflow_runtime import build_configurable_thread


class PocState(TypedDict, total=False):
    request: str
    events: list[str]
    decision: str
    approved: bool


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


def _snapshot_to_dict(snapshot: Any) -> dict[str, Any]:
    return {
        "next": list(getattr(snapshot, "next", ()) or ()),
        "values": getattr(snapshot, "values", {}),
        "config": getattr(snapshot, "config", {}),
        "metadata": getattr(snapshot, "metadata", {}),
    }


def prepare_request(state: PocState) -> dict[str, Any]:
    events = list(state.get("events", []) or [])
    events.append(f"request={state.get('request', '')}")
    return {"events": events}


def human_review(state: PocState) -> dict[str, Any]:
    approved = bool(
        interrupt(
            {
                "kind": "approval",
                "question": "Approve deterministic repair patch?",
                "request": state.get("request", ""),
                "recommended": True,
            }
        )
    )
    events = list(state.get("events", []) or [])
    events.append(f"human_approved={approved}")
    return {
        "approved": approved,
        "decision": "approved" if approved else "rejected",
        "events": events,
    }


def route_after_review(state: PocState) -> str:
    return "apply_patch" if state.get("approved") else "abort"


def apply_patch(state: PocState) -> dict[str, Any]:
    events = list(state.get("events", []) or [])
    events.append("apply_patch")
    return {
        "decision": "patched",
        "events": events,
    }


def abort(state: PocState) -> dict[str, Any]:
    events = list(state.get("events", []) or [])
    events.append("abort")
    return {
        "decision": "aborted",
        "events": events,
    }


def build_graph():
    builder = StateGraph(PocState)
    builder.add_node("prepare_request", prepare_request)
    builder.add_node("human_review", human_review)
    builder.add_node("apply_patch", apply_patch)
    builder.add_node("abort", abort)
    builder.add_edge(START, "prepare_request")
    builder.add_edge("prepare_request", "human_review")
    builder.add_conditional_edges(
        "human_review",
        route_after_review,
        {
            "apply_patch": "apply_patch",
            "abort": "abort",
        },
    )
    builder.add_edge("apply_patch", END)
    builder.add_edge("abort", END)
    return builder.compile(checkpointer=InMemorySaver())


def run_poc(thread_id: str, resume_value: bool) -> None:
    graph = build_graph()
    config = {"configurable": build_configurable_thread(thread_id)}
    initial_input: PocState = {
        "request": "repair compile wire port overflow",
        "events": [],
        "decision": "",
        "approved": False,
    }

    print("=== First invoke: expect interrupt ===")
    first_result = graph.invoke(initial_input, config)
    print(_json(first_result))

    paused_state = graph.get_state(config)
    print("=== Paused state via get_state ===")
    print(_json(_snapshot_to_dict(paused_state)))

    print("=== Resume with Command ===")
    final_result = graph.invoke(Command(resume=resume_value), config)
    print(_json(final_result))

    final_state = graph.get_state(config)
    print("=== Final state via get_state ===")
    print(_json(_snapshot_to_dict(final_state)))

    history = list(graph.get_state_history(config))
    print("=== State history via get_state_history ===")
    for index, snapshot in enumerate(history, start=1):
        print(f"-- snapshot {index} --")
        print(_json(_snapshot_to_dict(snapshot)))

    before_review = next((snapshot for snapshot in history if tuple(snapshot.next) == ("human_review",)), None)
    if before_review is None:
        print("No checkpoint found before human_review; skip replay demo.")
        return

    print("=== Fork from checkpoint before human_review ===")
    fork_config = graph.update_state(
        before_review.config,
        {
            "events": ["forked-before-review"],
            "approved": False,
            "decision": "",
        },
    )
    print(_json(fork_config))

    fork_pause = graph.invoke(None, fork_config)
    print("=== Forked run pauses at interrupt ===")
    print(_json(fork_pause))

    fork_resume_value = not resume_value
    print(f"=== Resume fork with Command(resume={fork_resume_value}) ===")
    fork_result = graph.invoke(Command(resume=fork_resume_value), fork_config)
    print(_json(fork_result))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Phase 4 HITL / persistence POC.")
    parser.add_argument(
        "--thread-id",
        default="phase4-hitl-demo",
        help="Thread id used by the checkpointer.",
    )
    parser.add_argument(
        "--resume",
        choices=["approve", "reject"],
        default="approve",
        help="How to resume the interrupt.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_poc(
        thread_id=args.thread_id,
        resume_value=args.resume == "approve",
    )


if __name__ == "__main__":
    main()
