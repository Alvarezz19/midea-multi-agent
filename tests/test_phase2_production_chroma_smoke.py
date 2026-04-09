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

from chromadb.api.shared_system_client import SharedSystemClient
from chromadb.api.types import Embeddable, EmbeddingFunction, Embeddings
from chromadb.utils.embedding_functions import register_embedding_function


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
from agents.retrieval_agent import RetrievalAgent
from utils.ahu_knowledge_builder import build_ahu_knowledge_assets, write_assets_to_chroma
from utils.model_manager import EmbeddingManager


@register_embedding_function
class Phase2ProductionEmbeddingFunction(EmbeddingFunction[Embeddable]):
    TERMS = ("ahu", "送风机", "电加热", "冷水阀", "直膨", "control", "template", "pattern")

    def __init__(self) -> None:
        pass

    def __call__(self, input: Embeddable) -> Embeddings:
        texts = [input] if isinstance(input, str) else list(input)
        embeddings = []
        for text in texts:
            lowered = str(text).lower()
            embeddings.append([float(lowered.count(term.lower())) for term in self.TERMS])
        return embeddings

    @staticmethod
    def name() -> str:
        return "phase2_production_embedding"

    @staticmethod
    def build_from_config(config_data: dict[str, Any]) -> "Phase2ProductionEmbeddingFunction":
        Phase2ProductionEmbeddingFunction.validate_config(config_data)
        return Phase2ProductionEmbeddingFunction()

    def get_config(self) -> dict[str, Any]:
        return {}


def make_analysis_result() -> dict:
    return {
        "retrieval_plan": {
            "queries": ["AHU 送风机 电加热 联动控制", "送风机标准控制", "电加热标准控制"],
            "intent": "general_query",
            "detected_operations": [],
            "keywords": ["AHU", "送风机", "电加热"],
        },
        "scenario_analysis": {
            "summary": "AHU 送风机与电加热联动控制",
            "business_goal": "送风机与电加热联动控制",
            "system_type": "AHU",
            "equipment_object": "送风机、电加热",
            "actuator": "送风机、电加热",
            "control_strategy": "标准控制 + 联锁",
            "control_mode": "手/自动，定时启停",
            "input_signals": ["送风机运行状态", "送风机启停手/自动"],
            "output_signals": ["送风机可用标志", "电加热启停命令"],
        },
    }


class Phase2ProductionChromaSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.output_dir = Path(tempfile.mkdtemp(prefix="phase2-pattern-library-"))
        self.persist_dir = Path(tempfile.mkdtemp(prefix="phase2-production-chroma-"))
        self.addCleanup(self._cleanup_dirs)
        self.embedding_function = Phase2ProductionEmbeddingFunction()

    def _cleanup_dirs(self) -> None:
        SharedSystemClient.clear_system_cache()
        self.embedding_function = None
        gc.collect()
        shutil.rmtree(self.output_dir, ignore_errors=True)
        shutil.rmtree(self.persist_dir, ignore_errors=True)

    def test_build_write_and_retrieve_round_trip_with_real_ahu_assets(self) -> None:
        assets = build_ahu_knowledge_assets(
            flows_dir=PROJECT_ROOT / "AHU程序",
            output_dir=self.output_dir,
        )

        with patch.object(EmbeddingManager, "get_embedding", return_value=self.embedding_function):
            written = write_assets_to_chroma(assets, persist_dir=self.persist_dir)

        self.assertGreaterEqual(written["subflow_templates"], 1)
        self.assertGreaterEqual(written["system_patterns"], 1)
        manifest = assets["manifest"]
        self.assertEqual(manifest["asset_chain_role"], "rebuildable_cache")
        self.assertEqual(manifest["persist_dir"], str(self.persist_dir))
        self.assertTrue(manifest["source_flows"])
        self.assertTrue(all(item.get("sha1") for item in manifest["source_flows"]))
        self.assertIn("subflow_templates", manifest["collection_names"])
        self.assertIn("system_patterns", manifest["collection_names"])

        manifest_path = self.output_dir / "manifest.json"
        saved_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(saved_manifest["persist_dir"], str(self.persist_dir))
        self.assertEqual(saved_manifest["collection_owner"], config.PHASE2_CHROMA_COLLECTION_OWNER)

        with patch.object(config, "CHROMA_PERSIST_DIR", str(self.persist_dir)), \
             patch.object(config, "DEBUG", False), \
             patch.object(EmbeddingManager, "get_embedding", return_value=self.embedding_function):
            agent = RetrievalAgent()
            bundle = agent.retrieve_bundle(
                "AHU 送风机 电加热 联动控制",
                similarity_threshold=0.0,
                analysis_result=make_analysis_result(),
            )

        self.assertGreaterEqual(bundle["metadata"]["retrieved_subflow_count"], 2)
        self.assertGreaterEqual(bundle["metadata"]["retrieved_pattern_count"], 1)
        self.assertTrue(bundle["metadata"]["selected_case_pattern_id"])
        retrieved_roles = {item.get("template_role") for item in bundle["subflow_templates"]}
        self.assertIn("supply_fan_control", retrieved_roles)


if __name__ == "__main__":
    unittest.main()
