from __future__ import annotations

import gc
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import chromadb
from chromadb.api.shared_system_client import SharedSystemClient
from chromadb.api.types import Embeddable, EmbeddingFunction, Embeddings
from chromadb.utils.embedding_functions import register_embedding_function

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
import workflow_trace
from utils.ahu_knowledge_builder import build_ahu_knowledge_assets, write_assets_to_chroma
from utils.model_manager import EmbeddingManager, LLMManager


OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "phase4_smoke"


@register_embedding_function
class Phase4SmokeEmbeddingFunction(EmbeddingFunction[Embeddable]):
    def __init__(self) -> None:
        pass

    def __call__(self, input: Embeddable) -> Embeddings:
        texts = [input] if isinstance(input, str) else list(input)
        embeddings = []
        for text in texts:
            lowered = str(text).lower()
            embeddings.append(
                [
                    1.0 if any(token in lowered for token in ("送风机", "supply_fan_control")) else 0.0,
                    1.0 if any(token in lowered for token in ("电加热", "heater_control")) else 0.0,
                    1.0 if any(token in lowered for token in ("冷水阀", "chw_valve_control", "chilled water")) else 0.0,
                    1.0 if "ahu" in lowered or "空调" in lowered else 0.0,
                ]
            )
        return embeddings

    @staticmethod
    def name() -> str:
        return "phase4_smoke_embedding"

    @staticmethod
    def build_from_config(config_data: dict[str, Any]) -> "Phase4SmokeEmbeddingFunction":
        Phase4SmokeEmbeddingFunction.validate_config(config_data)
        return Phase4SmokeEmbeddingFunction()

    def get_config(self) -> dict[str, Any]:
        return {}


class FakeStructuredResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def model_dump(self) -> dict[str, Any]:
        return json.loads(json.dumps(self.payload, ensure_ascii=False))


class FakeStructuredLLM:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def invoke(self, messages) -> FakeStructuredResponse:
        del messages
        return FakeStructuredResponse(self.payload)


class FakeAnalysisLLM:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def with_structured_output(self, schema, method="function_calling") -> FakeStructuredLLM:
        del schema, method
        return FakeStructuredLLM(self.payload)

    def invoke(self, messages):
        del messages
        return type("FakeResponse", (), {"content": json.dumps(self.payload, ensure_ascii=False)})()


def _atomic_module_payload() -> dict[str, Any]:
    return {
        "module_type": "constInput",
        "name": "外部输入占位",
        "description": "Provide a placeholder source for external AHU inputs.",
        "category": "logic/basic",
        "parameters_schema": {
            "name": {"type": "string", "description": "signal name"},
            "fixedValue": {"type": "number", "description": "constant value"},
        },
        "ports_definition": {
            "inputs": [],
            "outputs": [{"index": 0, "label": "out", "type": "number", "description": "output"}],
        },
        "template_json": {"type": "constInput", "inputs": 0, "outputs": 1},
        "keywords": ["AHU", "送风机", "占位输入"],
        "usage_guides": ["Use when an external input signal needs a deterministic placeholder source."],
    }


def _populate_chroma(persist_dir: Path, embedding_function: EmbeddingFunction[Embeddable]) -> None:
    assets = build_ahu_knowledge_assets(output_dir=None)
    with patch.object(EmbeddingManager, "get_embedding", return_value=embedding_function):
        write_assets_to_chroma(assets, persist_dir=persist_dir)

    client = chromadb.PersistentClient(path=str(persist_dir))
    atomic_collection = client.get_or_create_collection(
        name=config.CHROMA_COLLECTION_ATOMIC_MODULES,
        embedding_function=embedding_function,
        metadata={"description": "phase4 smoke atomic modules"},
    )
    atomic_payload = _atomic_module_payload()
    atomic_collection.upsert(
        documents=["AHU 外部输入 占位源"],
        metadatas=[
            {
                "module_type": atomic_payload["module_type"],
                "category": atomic_payload["category"],
                "json_schema": json.dumps(atomic_payload, ensure_ascii=False),
            }
        ],
        ids=["atomic_constInput_phase4_smoke"],
    )


def _single_fan_payload() -> dict[str, Any]:
    return {
        "retrieval_plan": {
            "queries": ["AHU 送风机标准控制", "送风机标准控制"],
            "category_l1": "",
            "intent": "general_query",
            "detected_operations": [],
            "keywords": ["AHU", "送风机", "标准控制"],
        },
        "scenario_analysis": {
            "summary": "AHU 送风机标准控制",
            "business_goal": "AHU 送风机标准控制 supply_fan_control",
            "system_type": "AHU",
            "equipment_object": "送风机 supply_fan_control",
            "actuator": "送风机 supply_fan_control",
            "controlled_variable": "送风机运行状态",
            "feedback_variable": "送风机运行状态",
            "setpoint_variable": "送风机启停自动控制命令",
            "output_signal": "送风机启停最终控制命令",
            "control_strategy": "标准控制",
            "control_mode": "手/自动，定时启停",
            "input_signals": [
                "送风机运行状态",
                "送风机故障状态",
                "送风机本地/远程",
                "送风机压差状态",
                "送风机启停手/自动",
                "送风机启停手动控制命令",
                "送风机启停自动控制命令",
                "送风机缺风报警延时设定值",
                "送风机故障报警复位",
            ],
            "output_signals": [
                "送风机运行标志",
                "送风机启停最终控制命令",
                "送风机故障标志",
                "送风机可用标志",
            ],
            "operating_conditions": ["定时启停"],
            "interlocks_or_limits": ["送风机故障联锁"],
            "calculation_logic": [],
            "ambiguities": [],
            "assumptions": [],
            "confidence": 0.92,
        },
    }


def _fan_chw_heater_payload() -> dict[str, Any]:
    return {
        "retrieval_plan": {
            "queries": ["AHU 送风机 冷水阀 电加热 联动控制", "送风机标准控制", "冷水阀标准控制", "电加热标准控制"],
            "category_l1": "",
            "intent": "general_query",
            "detected_operations": [],
            "keywords": ["AHU", "送风机", "冷水阀", "电加热", "联动控制"],
        },
        "scenario_analysis": {
            "summary": "AHU 送风机、冷水阀与电加热联动控制",
            "business_goal": "AHU 送风机、冷水阀与电加热联动控制 supply_fan_control chw_valve_control heater_control",
            "system_type": "AHU",
            "equipment_object": "送风机、冷水阀、电加热 supply_fan_control chw_valve_control heater_control",
            "actuator": "送风机、冷水阀、电加热 supply_fan_control chw_valve_control heater_control",
            "controlled_variable": "送风温度",
            "feedback_variable": "送风温度",
            "setpoint_variable": "送风温度设定值",
            "output_signal": "送风机可用标志、冷水阀开度最终控制命令、电加热控制值",
            "control_strategy": "模板复用 + 联动控制",
            "control_mode": "手/自动，定时启停",
            "input_signals": [
                "送风机运行状态",
                "送风机故障状态",
                "送风机启停手/自动",
                "送风温度设定值",
                "送风温度",
                "电加热故障",
            ],
            "output_signals": [
                "送风机可用标志",
                "冷水阀开度最终控制命令",
                "电加热控制值",
            ],
            "operating_conditions": ["定时启停"],
            "interlocks_or_limits": ["送风机故障联锁"],
            "calculation_logic": [],
            "ambiguities": [],
            "assumptions": [],
            "confidence": 0.93,
        },
    }


def _payload_for_query(query: str) -> dict[str, Any]:
    if query == "为 AHU 生成送风机标准控制":
        return _single_fan_payload()
    if query == "为 AHU 生成送风机、冷水阀与电加热联动控制":
        return _fan_chw_heater_payload()
    raise ValueError(f"Unsupported smoke query: {query}")


def _run_query_smoke(run_dir: Path, persist_dir: Path, embedding_function: EmbeddingFunction[Embeddable], query: str) -> dict[str, Any]:
    fake_llm = FakeAnalysisLLM(_payload_for_query(query))
    with patch.object(config, "DEBUG", False), \
         patch.object(config, "CHROMA_PERSIST_DIR", str(persist_dir)), \
         patch.object(EmbeddingManager, "get_embedding", return_value=embedding_function), \
         patch.object(LLMManager, "get_llm", return_value=fake_llm):
        result = workflow_trace.run_workflow(query)

    verification_report = result.get("verification_report", {}) or {}
    route_decision = result.get("route_decision", {}) or {}
    workflow_trace_info = (result.get("final_output", {}) or {}).get("workflow_trace", {}) or {}
    unresolved_item_types = sorted(
        {
            str(item.get("type", "")).strip()
            for item in (result.get("assembled_graph_ir", {}) or {}).get("unresolved_items", []) or []
            if str(item.get("type", "")).strip()
        }
    )
    summary = {
        "query": query,
        "verification_status": verification_report.get("status", ""),
        "repair_scope": verification_report.get("repair_scope", ""),
        "route_decision": route_decision.get("decision", ""),
        "trace_dir": workflow_trace_info.get("trace_dir", ""),
        "unresolved_item_types": unresolved_item_types,
    }
    return summary


def main() -> int:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = OUTPUT_ROOT / f"smoke_{timestamp}"
    persist_dir = run_dir / "smoke_chroma"
    run_dir.mkdir(parents=True, exist_ok=True)

    embedding_function = Phase4SmokeEmbeddingFunction()
    summaries: list[dict[str, Any]] = []
    queries = [
        "为 AHU 生成送风机标准控制",
        "为 AHU 生成送风机、冷水阀与电加热联动控制",
    ]

    try:
        _populate_chroma(persist_dir, embedding_function)
        for query in queries:
            summaries.append(_run_query_smoke(run_dir, persist_dir, embedding_function, query))
    finally:
        SharedSystemClient.clear_system_cache()
        gc.collect()

    summary_json = run_dir / "phase4_smoke_summary.json"
    summary_md = run_dir / "phase4_smoke_summary.md"
    summary_json.write_text(json.dumps({"results": summaries}, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines = ["# Phase 4 Query Smoke", "", f"- 生成时间：{datetime.now().isoformat(timespec='seconds')}", ""]
    for item in summaries:
        md_lines.extend(
            [
                f"## {item['query']}",
                f"- verification_status: `{item['verification_status']}`",
                f"- repair_scope: `{item['repair_scope']}`",
                f"- route_decision: `{item['route_decision']}`",
                f"- trace_dir: `{item['trace_dir']}`",
                f"- unresolved_item_types: `{', '.join(item['unresolved_item_types'])}`",
                "",
            ]
        )
    summary_md.write_text("\n".join(md_lines), encoding="utf-8")

    print(f"Smoke summary written to: {summary_md}")
    for item in summaries:
        print(
            json.dumps(
                {
                    "query": item["query"],
                    "verification_status": item["verification_status"],
                    "repair_scope": item["repair_scope"],
                    "route_decision": item["route_decision"],
                    "trace_dir": item["trace_dir"],
                    "unresolved_item_types": item["unresolved_item_types"],
                },
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
