from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import config
from agents.llm_enhancers.retrieval_rewrite import RetrievalQueryRewriter
from tests.retrieval_agent_phase2_shared import RetrievalAgentPhase2ChromaHarness
from utils.model_manager import LLMManager


class FakeStructuredResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def model_dump(self) -> dict:
        return json.loads(json.dumps(self.payload, ensure_ascii=False))


class FakeStructuredLLM:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def invoke(self, messages) -> FakeStructuredResponse:
        del messages
        return FakeStructuredResponse(self.payload)


class FakeRewriteLLM:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def with_structured_output(self, schema, method="function_calling") -> FakeStructuredLLM:
        del schema, method
        return FakeStructuredLLM(self.payload)

    def invoke(self, messages):
        del messages
        return type("FakeResponse", (), {"content": json.dumps(self.payload, ensure_ascii=False)})()


class FailingLLM:
    def with_structured_output(self, schema, method="function_calling"):
        del schema, method
        raise RuntimeError("structured failed")

    def invoke(self, messages):
        del messages
        raise RuntimeError("invoke failed")


class RetrievalLlmEnhancerTests(RetrievalAgentPhase2ChromaHarness):
    def test_llm_rewrite_merges_query_variants_and_retrieves_assets(self):
        payload = {
            "query_variants": ["fan control", "AHU fan control"],
            "template_queries": ["fan control template"],
            "pattern_queries": ["AHU pattern"],
            "normalized_terms": ["fan", "control"],
            "risk_flags": [],
        }

        with patch.object(config, "LLM_ENHANCEMENT_ENABLED", True), \
             patch.object(config, "RETRIEVAL_USE_LLM_REWRITE", True), \
             patch.object(LLMManager, "get_llm", return_value=FakeRewriteLLM(payload)), \
             self.agent_runtime() as agent:
            bundle = agent.retrieve_bundle(
                "unmatched request",
                similarity_threshold=0.0,
                analysis_result={"retrieval_plan": {"queries": []}, "scenario_analysis": {}},
            )

        self.assertTrue(bundle["metadata"]["llm_rewrite"]["enabled"])
        self.assertTrue(bundle["metadata"]["llm_rewrite"]["adopted"])
        self.assertIn("fan control", bundle["metadata"]["query_variants"])
        self.assertEqual(bundle["metadata"]["top_subflow_template_ids"], ["fan_template"])
        self.assertEqual(bundle["metadata"]["top_system_pattern_ids"], ["ahu_control_pattern_v1"])

    def test_llm_rewrite_requires_global_enhancement_switch(self):
        payload = {"query_variants": ["fan control"]}

        with patch.object(config, "LLM_ENHANCEMENT_ENABLED", False), \
             patch.object(config, "RETRIEVAL_USE_LLM_REWRITE", True), \
             patch.object(LLMManager, "get_llm", return_value=FakeRewriteLLM(payload)) as get_llm, \
             self.agent_runtime() as agent:
            bundle = agent.retrieve_bundle(
                "fan control",
                similarity_threshold=0.0,
                analysis_result={"retrieval_plan": {"queries": ["fan control"]}, "scenario_analysis": {}},
            )

        get_llm.assert_not_called()
        self.assertFalse(bundle["metadata"]["llm_rewrite"]["enabled"])
        self.assertEqual(bundle["metadata"]["top_subflow_template_ids"], ["fan_template"])

    def test_llm_rewrite_failure_falls_back_to_deterministic_queries(self):
        with patch.object(config, "LLM_ENHANCEMENT_ENABLED", True), \
             patch.object(config, "RETRIEVAL_USE_LLM_REWRITE", True), \
             patch.object(LLMManager, "get_llm", return_value=FailingLLM()), \
             self.agent_runtime() as agent:
            bundle = agent.retrieve_bundle(
                "fan control",
                similarity_threshold=0.0,
                analysis_result={"retrieval_plan": {"queries": ["fan control"]}, "scenario_analysis": {}},
            )

        self.assertTrue(bundle["metadata"]["llm_rewrite"]["fallback_used"])
        self.assertEqual(bundle["metadata"]["query_variants"], ["fan control"])
        self.assertEqual(bundle["metadata"]["top_subflow_template_ids"], ["fan_template"])

    def test_rewrite_result_is_normalized_and_limited(self):
        rewriter = RetrievalQueryRewriter(
            FakeRewriteLLM(
                {
                    "query_variants": ["a", "a", "", "b"],
                    "template_queries": ["c"],
                    "pattern_queries": ["d"],
                    "normalized_terms": ["x", "x"],
                }
            ),
            max_queries=3,
        )

        result = rewriter.rewrite("query", {}, {})

        self.assertEqual(result["rewrite"]["query_variants"], ["a", "b"])
        self.assertEqual(result["rewrite"]["template_queries"], ["c"])
        self.assertEqual(result["rewrite"]["pattern_queries"], [])
        self.assertEqual(result["rewrite"]["normalized_terms"], ["x"])


if __name__ == "__main__":
    unittest.main()
