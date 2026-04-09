from __future__ import annotations

import gc
import json
import shutil
import sys
import tempfile
import unittest
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
import workflow
import workflow_trace
from utils.ahu_knowledge_builder import build_ahu_knowledge_assets, write_assets_to_chroma
from utils.model_manager import EmbeddingManager, LLMManager
from utils.retrieval_bundle_utils import build_legacy_retrieval_context


def make_requirement_spec() -> dict:
    return {
        "schema_version": "3.0",
        "system_type": "AHU",
        "scenario_summary": "送风机控制",
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
        "signals": {"inputs": [], "outputs": [], "software_points": [], "alarm_points": []},
        "required_pages": ["IO/通讯", "控制", "定时"],
        "global_modes": ["schedule_enable"],
        "ambiguities": [],
        "assumptions": [],
        "acceptance_criteria": [],
        "confidence": 0.8,
        "warnings": [],
    }


def make_bundle() -> dict:
    return {
        "atomic_modules": [
            {
                "module_type": "constInput",
                "name": "Constant Input",
                "category": "logic/basic",
                "description": "Provide a constant numeric value.",
                "parameters_schema": {"fixedValue": {"type": "number"}},
                "ports_definition": {"inputs": [], "outputs": [{"index": 0, "label": "out"}]},
                "template_json": {"type": "constInput", "inputs": 0, "outputs": 1},
            }
        ],
        "subflow_templates": [
            {
                "module_type": "fan_template",
                "asset_type": "subflow_template",
                "template_id": "fan_template",
                "definition_id": "fan_template",
                "template_name": "送风机标准控制",
                "template_role": "supply_fan_control",
                "name": "送风机标准控制",
                "category": "AHU/subflow_templates/fan_control",
                "description": "Reusable fan control subflow.",
                "parameters_schema": {},
                "ports_definition": {
                    "inputs": [{"index": 0, "label": "schedule_enable"}],
                    "outputs": [{"index": 0, "label": "supply_fan_available_flag"}],
                },
                "template_json": {
                    "type": "subflow",
                    "id": "fan_template",
                    "name": "送风机标准控制",
                    "in": [{"x": 60, "y": 80, "name": "schedule_enable", "wires": []}],
                    "out": [{"x": 380, "y": 110, "name": "supply_fan_available_flag", "wires": []}],
                    "inputs": 1,
                    "outputs": 1,
                },
                "compile_hints": {"input_count": 1, "output_count": 1},
            }
        ],
        "system_patterns": [
            {
                "pattern_id": "ahu_test_pattern",
                "required_pages": [
                    {"page_key": "control", "label": "控制", "kind": "control"},
                    {"page_key": "io_comm", "label": "IO/通讯", "kind": "io"},
                ],
                "optional_pages": [{"page_key": "timing", "label": "定时", "kind": "timing"}],
            }
        ],
        "style_guides": [],
        "metadata": {"selected_case_pattern_id": "ahu_test_pattern"},
    }


class StubAnalysis:
    def __call__(self, state):
        state["analysis_result"] = {
            "scenario_analysis": {
                "summary": "送风机控制",
                "system_type": "AHU",
                "input_signals": ["schedule_enable"],
                "output_signals": ["supply_fan_available_flag"],
            }
        }
        state["requirement_spec"] = make_requirement_spec()
        state["current_step"] = "analysis_completed"
        return state


class StubRetrieval:
    def __call__(self, state):
        bundle = make_bundle()
        state["retrieval_bundle"] = bundle
        state["retrieval_context"] = build_legacy_retrieval_context(bundle)
        state["current_step"] = "retrieval_completed"
        return state


@register_embedding_function
class Phase3WorkflowEmbeddingFunction(EmbeddingFunction[Embeddable]):
    def __init__(self) -> None:
        pass

    def __call__(self, input: Embeddable) -> Embeddings:
        texts = [input] if isinstance(input, str) else list(input)
        embeddings = []
        for text in texts:
            lowered = str(text).lower()
            vector = [
                1.0 if any(token in lowered for token in ("送风机", "supply_fan_control")) else 0.0,
                1.0 if any(token in lowered for token in ("电加热", "heater_control")) else 0.0,
                1.0 if any(token in lowered for token in ("直膨", "dx_control")) else 0.0,
                1.0 if any(token in lowered for token in ("冷水阀", "chw_valve_control", "chilled water")) else 0.0,
                1.0 if any(token in lowered for token in ("ahu", "空调")) else 0.0,
            ]
            embeddings.append(vector)
        return embeddings

    @staticmethod
    def name() -> str:
        return "phase3_workflow_test_embedding"

    @staticmethod
    def build_from_config(config_data: dict[str, Any]) -> "Phase3WorkflowEmbeddingFunction":
        Phase3WorkflowEmbeddingFunction.validate_config(config_data)
        return Phase3WorkflowEmbeddingFunction()

    def get_config(self) -> dict[str, Any]:
        return {}


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
            "outputs": [
                {
                    "index": 0,
                    "label": "out",
                    "type": "number",
                    "description": "output",
                }
            ],
        },
        "template_json": {"type": "constInput", "inputs": 0, "outputs": 1},
        "keywords": ["AHU", "送风机", "占位输入"],
        "usage_guides": ["Use when an external input signal needs a deterministic placeholder source."],
    }


def _real_analysis_result() -> dict:
    return {
        "retrieval_plan": {
            "queries": ["AHU 末端组空送风机标准控制", "送风机标准控制", "末端组空送风机"],
            "category_l1": "",
            "intent": "general_query",
            "detected_operations": [],
            "keywords": ["AHU", "送风机", "标准控制", "启停"],
        },
        "scenario_analysis": {
            "summary": "AHU 送风机标准控制",
            "business_goal": "末端组空送风机标准控制",
            "system_type": "AHU",
            "equipment_object": "末端组空送风机",
            "actuator": "送风机",
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
                "送风机故障报警延时设定值",
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


def _real_multisubsystem_analysis_result(case_name: str) -> dict:
    cases = {
        "fan_heater": {
            "query": "为 AHU 生成送风机与电加热联动控制",
            "retrieval_queries": ["AHU 送风机 电加热 联动控制", "送风机标准控制", "电加热标准控制"],
            "summary": "AHU 送风机与电加热联动控制",
            "business_goal": "末端组空送风机与电加热联动控制 supply_fan_control heater_control",
            "equipment_object": "末端组空送风机、电加热 supply_fan_control heater_control",
            "actuator": "送风机、电加热 supply_fan_control heater_control",
            "controlled_variable": "送风温度",
            "output_signal": "送风机可用标志、电加热启停命令",
            "control_strategy": "标准控制 + 联锁",
            "input_signals": ["送风机运行状态", "送风机故障状态", "送风机启停手/自动"],
            "output_signals": ["送风机可用标志", "电加热启停命令"],
            "operating_conditions": ["定时启停"],
            "interlocks": ["送风机故障联锁"],
        },
        "fan_chw": {
            "query": "为 AHU 生成送风机与冷水阀联动控制",
            "retrieval_queries": ["AHU 送风机 冷水阀 联动控制", "送风机标准控制", "冷水阀标准控制"],
            "summary": "AHU 送风机与冷水阀联动控制",
            "business_goal": "送风机与冷水阀联动调节送风温度 supply_fan_control chw_valve_control",
            "equipment_object": "送风机、冷水阀 supply_fan_control chw_valve_control",
            "actuator": "送风机、冷水阀 supply_fan_control chw_valve_control",
            "controlled_variable": "送风温度",
            "output_signal": "送风机可用标志、冷水阀开度命令",
            "control_strategy": "PID + 联锁",
            "input_signals": ["送风温度", "送风机运行状态", "送风机启停手/自动"],
            "output_signals": ["送风机可用标志", "冷水阀开度命令"],
            "operating_conditions": ["定时启停"],
            "interlocks": ["送风机故障联锁"],
        },
        "fan_dx": {
            "query": "为 AHU 生成送风机与直膨联动控制",
            "retrieval_queries": ["AHU 送风机 直膨 联动控制", "送风机标准控制", "直膨标准控制"],
            "summary": "AHU 送风机与直膨联动控制",
            "business_goal": "送风机与直膨机组联动控制 supply_fan_control dx_control",
            "equipment_object": "送风机、直膨机组 supply_fan_control dx_control",
            "actuator": "送风机、直膨 supply_fan_control dx_control",
            "controlled_variable": "送风温度",
            "output_signal": "送风机可用标志、直膨运行命令",
            "control_strategy": "标准控制 + 联锁",
            "input_signals": ["送风机运行状态", "送风机故障状态", "送风机启停手/自动"],
            "output_signals": ["送风机可用标志", "直膨运行命令"],
            "operating_conditions": ["定时启停"],
            "interlocks": ["送风机故障联锁", "直膨机状态联锁"],
        },
    }
    case = cases[case_name]
    return {
        "retrieval_plan": {
            "queries": case["retrieval_queries"],
            "category_l1": "",
            "intent": "general_query",
            "detected_operations": [],
            "keywords": ["AHU", "送风机"],
        },
        "scenario_analysis": {
            "summary": case["summary"],
            "business_goal": case["business_goal"],
            "system_type": "AHU",
            "equipment_object": case["equipment_object"],
            "actuator": case["actuator"],
            "controlled_variable": case["controlled_variable"],
            "feedback_variable": case["controlled_variable"],
            "setpoint_variable": "送风温度设定值",
            "output_signal": case["output_signal"],
            "control_strategy": case["control_strategy"],
            "control_mode": "手/自动，定时启停",
            "input_signals": case["input_signals"],
            "output_signals": case["output_signals"],
            "operating_conditions": case["operating_conditions"],
            "interlocks_or_limits": case["interlocks"],
            "calculation_logic": [],
            "ambiguities": [],
            "assumptions": [],
            "confidence": 0.93,
        },
    }


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


def _populate_real_phase3_chroma(persist_dir: Path, embedding_function: EmbeddingFunction[Embeddable]) -> None:
    assets = build_ahu_knowledge_assets(output_dir=None)

    with patch.object(EmbeddingManager, "get_embedding", return_value=embedding_function):
        write_assets_to_chroma(assets, persist_dir=persist_dir)

    client = chromadb.PersistentClient(path=str(persist_dir))
    atomic_collection = client.get_or_create_collection(
        name=config.CHROMA_COLLECTION_ATOMIC_MODULES,
        embedding_function=embedding_function,
        metadata={"description": "phase3 atomic modules"},
    )
    atomic_payload = _atomic_module_payload()
    atomic_collection.upsert(
        documents=["AHU 送风机 外部输入 占位源"],
        metadatas=[
            {
                "module_type": atomic_payload["module_type"],
                "category": atomic_payload["category"],
                "json_schema": json.dumps(atomic_payload, ensure_ascii=False),
            }
        ],
        ids=["atomic_constInput_phase3"],
    )


class Phase3WorkflowTests(unittest.TestCase):
    def test_workflow_runs_phase3_linear_chain(self):
        with patch.object(config, "DEBUG", False), \
             patch.object(workflow, "AnalysisAgent", StubAnalysis), \
             patch.object(workflow, "RetrievalAgent", StubRetrieval):
            result = workflow.run_workflow("送风机控制")

        self.assertIn("decomposition_result", result)
        self.assertIn("architecture_plan", result)
        self.assertIn("subsystem_plan_map", result)
        self.assertIn("assembled_graph_ir", result)
        self.assertTrue(result["execution_plan"]["nodes"])
        self.assertEqual(result["verification_report"]["status"], "passed")
        self.assertEqual(result["final_output"]["verification_report"]["status"], "passed")

    def test_workflow_trace_records_phase3_fields(self):
        with patch.object(config, "DEBUG", False), \
             patch.object(workflow_trace, "AnalysisAgent", StubAnalysis), \
             patch.object(workflow_trace, "RetrievalAgent", StubRetrieval), \
             patch.object(workflow_trace, "_save_workflow_trace", return_value={"trace_dir": "mock-trace"}):
            result = workflow_trace.run_workflow("送风机控制")

        self.assertEqual(result["verification_report"]["status"], "passed")
        self.assertEqual(result["final_output"]["workflow_trace"]["trace_dir"], "mock-trace")
        self.assertIn("architecture_plan", result)
        self.assertIn("subsystem_plan_map", result)


class Phase3WorkflowTraceSummaryTests(unittest.TestCase):
    def test_build_trace_summary_collects_phase3_acceptance_fields(self):
        final_state = workflow.build_initial_state("送风机控制")
        bundle = make_bundle()
        bundle["metadata"].update(
            {
                "retrieved_atomic_count": 1,
                "retrieved_subflow_count": 1,
                "retrieved_pattern_count": 1,
            }
        )
        final_state["retrieval_bundle"] = bundle
        final_state["subsystem_plan_map"] = {
            "supply_fan_ctrl": {"implementation_mode": "reuse_template"},
            "heater_ctrl": {"implementation_mode": "atomic_assembly"},
        }
        final_state["assembled_graph_ir"] = {
            "unresolved_items": [
                {"type": "synthetic_shared_signal_source", "severity": "error"},
                {"type": "layout_hint_missing", "severity": "warning"},
            ]
        }
        final_state["compiled_artifact"] = {
            "compile_report": {"page_count": 2, "subflow_count": 1, "node_count": 5}
        }
        final_state["verification_report"] = {
            "status": "retryable_error",
            "repair_scope": "planning",
            "issue_summary": "发现 1 个结构错误。",
            "issues": [{"issue_id": "V-001"}],
            "warnings": ["布局建议缺失"],
            "metrics": {
                "missing_required_inputs": 1,
                "isolated_nodes": 0,
                "invalid_port_refs": 2,
            },
        }
        node_io_records = [
            {"node_name": "analysis", "status": "success", "output": {}},
            {"node_name": "retrieval", "status": "success", "output": {}},
            {"node_name": "verification", "status": "success", "output": {}},
        ]

        summary = workflow_trace._build_trace_summary(
            user_query="送风机控制",
            node_io_records=node_io_records,
            final_state=final_state,
            total_elapsed_seconds=12.34,
        )

        self.assertEqual(summary["workflow_status"], "retryable_error")
        self.assertEqual(summary["selected_case_pattern_id"], "ahu_test_pattern")
        self.assertEqual(summary["retrieved_atomic_count"], 1)
        self.assertEqual(summary["retrieved_subflow_count"], 1)
        self.assertEqual(summary["retrieved_pattern_count"], 1)
        self.assertEqual(summary["reuse_template_subsystem_count"], 1)
        self.assertEqual(summary["atomic_assembly_subsystem_count"], 1)
        self.assertEqual(summary["unresolved_item_count"], 2)
        self.assertEqual(summary["unresolved_error_count"], 1)
        self.assertEqual(summary["unresolved_warning_count"], 1)
        self.assertEqual(summary["verification_repair_scope"], "planning")
        self.assertEqual(summary["verification_error_count"], 1)
        self.assertEqual(summary["verification_warning_count"], 1)
        self.assertEqual(summary["verification_metrics"]["invalid_port_refs"], 2)
        self.assertIn("synthetic_shared_signal_source", summary["unresolved_item_types"])
        self.assertIn("status=retryable_error", summary["acceptance_summary"])

    def test_build_trace_summary_marks_failed_node_and_last_successful_node(self):
        summary = workflow_trace._build_trace_summary(
            user_query="boom",
            node_io_records=[
                {"node_name": "analysis", "status": "success", "output": {}},
                {
                    "node_name": "retrieval",
                    "status": "error",
                    "output": {"error_type": "RuntimeError", "error_message": "retrieval exploded"},
                },
            ],
            final_state=workflow.build_initial_state("boom"),
            total_elapsed_seconds=1.23,
        )

        self.assertEqual(summary["workflow_status"], "failed")
        self.assertEqual(summary["failed_node"], "retrieval")
        self.assertEqual(summary["error_type"], "RuntimeError")
        self.assertEqual(summary["error_message"], "retrieval exploded")
        self.assertEqual(summary["last_successful_node"], "analysis")
        self.assertEqual(summary["verification_status"], "")


class Phase3WorkflowRealIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.persist_dir = Path(tempfile.mkdtemp(prefix="phase3-workflow-real-"))
        self.addCleanup(self._cleanup_persist_dir)
        self.embedding_function = Phase3WorkflowEmbeddingFunction()
        _populate_real_phase3_chroma(self.persist_dir, self.embedding_function)

    def _cleanup_persist_dir(self) -> None:
        SharedSystemClient.clear_system_cache()
        self.embedding_function = None
        gc.collect()
        shutil.rmtree(self.persist_dir, ignore_errors=True)

    def test_workflow_runs_with_real_analysis_and_retrieval_agents(self):
        fake_llm = FakeAnalysisLLM(_real_analysis_result())

        with patch.object(config, "DEBUG", False), \
             patch.object(config, "CHROMA_PERSIST_DIR", str(self.persist_dir)), \
             patch.object(EmbeddingManager, "get_embedding", return_value=self.embedding_function), \
             patch.object(LLMManager, "get_llm", return_value=fake_llm):
            result = workflow.run_workflow("为 AHU 生成送风机标准控制")

        self.assertEqual(result["current_step"], "verification_completed")
        self.assertEqual(result["verification_report"]["status"], "passed")
        self.assertEqual(result["final_output"]["verification_report"]["status"], "passed")
        self.assertGreaterEqual(result["retrieval_bundle"]["metadata"]["retrieved_pattern_count"], 1)
        self.assertGreaterEqual(result["retrieval_bundle"]["metadata"]["retrieved_subflow_count"], 1)
        self.assertTrue(result["retrieval_bundle"]["metadata"]["selected_case_pattern_id"].startswith("ahu__"))
        self.assertTrue(result["architecture_plan"]["pattern_bindings"])
        self.assertEqual(result["subsystem_plan_map"]["supply_fan_ctrl"]["implementation_mode"], "reuse_template")
        self.assertTrue(
            result["subsystem_plan_map"]["supply_fan_ctrl"]["template_binding"]["template_id"].startswith("ahu_subflow__")
        )
        self.assertTrue(result["compiled_artifact"]["flow_objects"])
        self.assertTrue(result["execution_plan"]["nodes"])

    def test_workflow_runs_multi_subsystem_cases_with_real_phase2_assets(self):
        cases = {
            "fan_heater": {"subsystems": {"supply_fan_ctrl", "heater_ctrl"}},
            "fan_chw": {"subsystems": {"supply_fan_ctrl", "chw_valve_ctrl"}},
            "fan_dx": {"subsystems": {"supply_fan_ctrl", "dx_ctrl"}},
        }

        for case_name, expectation in cases.items():
            fake_llm = FakeAnalysisLLM(_real_multisubsystem_analysis_result(case_name))

            with self.subTest(case=case_name), \
                 patch.object(config, "DEBUG", False), \
                 patch.object(config, "CHROMA_PERSIST_DIR", str(self.persist_dir)), \
                 patch.object(EmbeddingManager, "get_embedding", return_value=self.embedding_function), \
                 patch.object(LLMManager, "get_llm", return_value=fake_llm):
                result = workflow.run_workflow(_real_multisubsystem_analysis_result(case_name)["scenario_analysis"]["summary"])

            self.assertEqual(result["verification_report"]["status"], "passed")
            self.assertTrue(expectation["subsystems"].issubset(set(result["subsystem_plan_map"].keys())))
            for subsystem_id in expectation["subsystems"]:
                self.assertEqual(result["subsystem_plan_map"][subsystem_id]["implementation_mode"], "reuse_template")
            unresolved_types = {
                item.get("type")
                for item in result["assembled_graph_ir"].get("unresolved_items", [])
            }
            self.assertNotIn("synthetic_shared_signal_source", unresolved_types)
            self.assertNotIn("ambiguous_shared_signal", unresolved_types)
            self.assertGreaterEqual(result["retrieval_bundle"]["metadata"]["retrieved_subflow_count"], 2)
            self.assertTrue(result["assembled_graph_ir"]["edges"])


if __name__ == "__main__":
    unittest.main()
