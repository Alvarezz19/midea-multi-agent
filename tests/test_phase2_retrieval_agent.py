from __future__ import annotations

import gc
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import contextmanager
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
from agents.retrieval_agent import RetrievalAgent
from utils.console_utils import safe_console_text
from utils.model_manager import EmbeddingManager


@register_embedding_function
class SimpleEmbeddingFunction(EmbeddingFunction[Embeddable]):
    TERMS = ("fan", "control", "ahu", "constant", "pattern", "run", "command")

    def __init__(self) -> None:
        pass

    def __call__(self, input: Embeddable) -> Embeddings:
        texts = [input] if isinstance(input, str) else list(input)
        embeddings = []
        for text in texts:
            lowered = str(text).lower()
            vector = [float(lowered.count(term)) for term in self.TERMS]
            embeddings.append(vector)
        return embeddings

    @staticmethod
    def name() -> str:
        return "simple_test_embedding"

    @staticmethod
    def build_from_config(config_data: dict[str, Any]) -> "SimpleEmbeddingFunction":
        SimpleEmbeddingFunction.validate_config(config_data)
        return SimpleEmbeddingFunction()

    def get_config(self) -> dict[str, Any]:
        return {}


def _atomic_module_payload() -> dict[str, Any]:
    return {
        "module_type": "constInput",
        "name": "Constant Input",
        "description": "Provide a constant numeric value.",
        "category": "logic/basic",
        "parameters_schema": {
            "fixedValue": {"type": "number", "description": "constant value"}
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
        "keywords": ["constant", "input"],
        "usage_guides": ["Use when a fixed numeric value is required."],
    }


def _subflow_template_payload() -> dict[str, Any]:
    return {
        "module_type": "fan_template",
        "asset_type": "subflow_template",
        "template_id": "fan_template",
        "definition_id": "fan_template",
        "template_name": "Fan Template",
        "template_role": "fan_control",
        "name": "Fan Template",
        "system_type": "AHU",
        "description": "Reusable AHU fan control template.",
        "category": "AHU/subflow_templates/fan_control",
        "parameters_schema": {},
        "ports_definition": {
            "inputs": [
                {
                    "index": 0,
                    "label": "run_cmd",
                    "type": "bool",
                    "description": "run command",
                }
            ],
            "outputs": [
                {
                    "index": 0,
                    "label": "run_feedback",
                    "type": "bool",
                    "description": "run feedback",
                }
            ],
        },
        "template_json": {
            "type": "subflow",
            "id": "fan_template",
            "name": "Fan Template",
            "in": [{"x": 60, "y": 80, "name": "run_cmd", "wires": []}],
            "out": [{"x": 380, "y": 80, "name": "run_feedback", "wires": []}],
            "inputs": 1,
            "outputs": 1,
        },
        "internal_flow_objects": [],
        "dependency_module_types": [],
        "compile_hints": {"supports_multi_instance": True},
        "source_info": {
            "source_flows": ["flows_20240101.json"],
            "original_subflow_id": "legacy_random_id",
        },
    }


def _system_pattern_payload() -> dict[str, Any]:
    return {
        "pattern_id": "ahu_control_pattern_v1",
        "pattern_name": "AHU Control Pattern",
        "system_type": "AHU",
        "description": "AHU pattern with control and timing pages.",
        "required_pages": [
            {"page_key": "control", "label": "Control", "kind": "control"}
        ],
        "optional_pages": [
            {"page_key": "timing", "label": "Timing", "kind": "timing"}
        ],
        "style_guides": {"layout": "compact", "naming": "ahu_std"},
        "source_cases": ["flows_20240101.json"],
    }


def _analysis_result() -> dict[str, Any]:
    return {
        "retrieval_plan": {
            "queries": ["fan control"],
            "intent": "general_query",
            "detected_operations": [],
            "keywords": ["fan", "control"],
        },
        "scenario_analysis": {
            "system_type": "AHU",
            "business_goal": "fan control",
            "equipment_object": "fan",
            "actuator": "fan",
            "control_strategy": "run control",
            "output_signal": "run command",
            "control_mode": "auto",
            "input_signals": ["run status"],
            "output_signals": ["run command"],
        },
    }


class RetrievalAgentPhase2ChromaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.persist_dir = Path(tempfile.mkdtemp(prefix="phase2-retrieval-agent-"))
        self.addCleanup(self._cleanup_persist_dir)
        self.embedding_function = SimpleEmbeddingFunction()
        self._populate_temp_chroma()

    def _cleanup_persist_dir(self) -> None:
        SharedSystemClient.clear_system_cache()
        self.embedding_function = None
        gc.collect()
        shutil.rmtree(self.persist_dir, ignore_errors=True)

    def _populate_temp_chroma(self) -> None:
        client = chromadb.PersistentClient(path=str(self.persist_dir))

        atomic_collection = client.get_or_create_collection(
            name=config.CHROMA_COLLECTION_ATOMIC_MODULES,
            embedding_function=self.embedding_function,
            metadata={"description": "atomic"},
        )
        atomic_payload = _atomic_module_payload()
        atomic_collection.upsert(
            documents=["constant input for fan control"],
            metadatas=[
                {
                    "module_type": atomic_payload["module_type"],
                    "category": atomic_payload["category"],
                    "json_schema": json.dumps(atomic_payload, ensure_ascii=False),
                }
            ],
            ids=["atomic_constInput"],
        )

        subflow_collection = client.get_or_create_collection(
            name=config.CHROMA_COLLECTION_SUBFLOW_TEMPLATES,
            embedding_function=self.embedding_function,
            metadata={"description": "subflow"},
        )
        subflow_payload = _subflow_template_payload()
        subflow_collection.upsert(
            documents=["fan control"],
            metadatas=[
                {
                    "module_type": subflow_payload["module_type"],
                    "asset_type": subflow_payload["asset_type"],
                    "payload_json": json.dumps(subflow_payload, ensure_ascii=False),
                }
            ],
            ids=["subflow_fan_template"],
        )

        pattern_collection = client.get_or_create_collection(
            name=config.CHROMA_COLLECTION_SYSTEM_PATTERNS,
            embedding_function=self.embedding_function,
            metadata={"description": "pattern"},
        )
        pattern_payload = _system_pattern_payload()
        pattern_collection.upsert(
            documents=["AHU"],
            metadatas=[
                {
                    "pattern_id": pattern_payload["pattern_id"],
                    "payload_json": json.dumps(pattern_payload, ensure_ascii=False),
                }
            ],
            ids=["pattern_ahu_control_pattern_v1"],
        )

    @contextmanager
    def _agent_runtime(self):
        with patch.object(config, "CHROMA_PERSIST_DIR", str(self.persist_dir)), patch.object(
            config, "DEBUG", False
        ), patch.object(
            EmbeddingManager, "get_embedding", return_value=self.embedding_function
        ):
            yield RetrievalAgent()

    def test_retrieve_bundle_reads_temp_chroma_phase2_collections(self) -> None:
        with self._agent_runtime() as agent:
            bundle = agent.retrieve_bundle(
                "fan control",
                similarity_threshold=0.0,
                analysis_result=_analysis_result(),
            )

        self.assertEqual(bundle["metadata"]["retrieved_atomic_count"], 1)
        self.assertEqual(bundle["metadata"]["retrieved_subflow_count"], 1)
        self.assertEqual(bundle["metadata"]["retrieved_pattern_count"], 1)
        self.assertTrue(bundle["metadata"]["rewrite_used"])
        self.assertTrue(bundle["metadata"]["analysis_used"])
        self.assertEqual(bundle["metadata"]["llm_queries"], ["fan control"])
        self.assertEqual(bundle["metadata"]["analysis_summary"], "")
        self.assertEqual(bundle["metadata"]["top_atomic_module_types"], ["constInput"])
        self.assertEqual(bundle["metadata"]["top_subflow_template_ids"], ["fan_template"])
        self.assertEqual(bundle["metadata"]["top_system_pattern_ids"], ["ahu_control_pattern_v1"])
        self.assertEqual(len(bundle["metadata"]["top_atomic_scores"]), 1)
        self.assertEqual(len(bundle["metadata"]["top_subflow_scores"]), 1)
        self.assertEqual(len(bundle["metadata"]["top_system_pattern_scores"]), 1)
        self.assertEqual(
            bundle["metadata"]["selected_case_pattern_id"], "ahu_control_pattern_v1"
        )
        self.assertEqual(bundle["atomic_modules"][0]["module_type"], "constInput")
        self.assertEqual(bundle["subflow_templates"][0]["template_id"], "fan_template")
        self.assertEqual(
            bundle["system_patterns"][0]["pattern_id"], "ahu_control_pattern_v1"
        )
        self.assertEqual(bundle["style_guides"][0]["layout"], "compact")

    def test_retrieve_returns_legacy_atomic_view_only(self) -> None:
        with self._agent_runtime() as agent:
            context = agent.retrieve(
                "fan control",
                similarity_threshold=0.0,
                analysis_result=_analysis_result(),
            )

        self.assertEqual(
            [node["module_type"] for node in context["relevant_nodes"]],
            ["constInput"],
        )
        self.assertEqual(context["metadata"]["retrieved_count"], 1)
        self.assertEqual(context["metadata"]["intent"], "general_query")

    def test_call_updates_state_with_real_temp_bundle(self) -> None:
        with self._agent_runtime() as agent:
            state = {
                "user_query": "fan control",
                "analysis_result": _analysis_result(),
            }
            result = agent(state)

        self.assertEqual(result["current_step"], "retrieval_completed")
        self.assertEqual(
            result["retrieval_bundle"]["subflow_templates"][0]["template_id"],
            "fan_template",
        )
        self.assertEqual(
            result["retrieval_bundle"]["system_patterns"][0]["pattern_id"],
            "ahu_control_pattern_v1",
        )
        self.assertEqual(
            [node["module_type"] for node in result["retrieval_context"]["relevant_nodes"]],
            ["constInput"],
        )

    def test_safe_console_text_replaces_unsupported_characters_for_gbk(self) -> None:
        class FakeStream:
            encoding = "gbk"

        text = safe_console_text(
            "\U0001F527 \u521d\u59cb\u5316Embedding",
            stream=FakeStream(),
        )
        self.assertNotIn("\U0001F527", text)
        self.assertIn("\u521d\u59cb\u5316Embedding", text)


if __name__ == "__main__":
    unittest.main()
