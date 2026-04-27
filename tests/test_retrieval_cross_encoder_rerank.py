from __future__ import annotations

import unittest
from unittest.mock import patch

import config
from agents.retrieval_agent import RetrievalAgent
from tests.retrieval_agent_phase2_shared import RetrievalAgentPhase2ChromaHarness
from utils.retrieval_rerank import rerank_retrieval_candidates


class FakeScorer:
    def __init__(self, scores: list[float]) -> None:
        self.scores = scores
        self.called = False

    def score_pairs(self, pairs):
        self.called = True
        return self.scores[: len(pairs)]


class FailingScorer:
    def score_pairs(self, pairs):
        del pairs
        raise RuntimeError("rerank failed")


class RetrievalCrossEncoderRerankTests(RetrievalAgentPhase2ChromaHarness):
    def test_rerank_reorders_existing_candidates_only(self):
        candidates = [
            {"template_id": "template_a", "description": "generic", "similarity_score": 0.9},
            {"template_id": "template_b", "description": "fan control", "similarity_score": 0.1},
        ]
        scorer = FakeScorer([0.1, 1.0])

        result = rerank_retrieval_candidates(
            candidates,
            query="fan control",
            scorer=scorer,
            asset_type="subflow_template",
            top_n=10,
        )

        self.assertFalse(result["fallback_used"])
        self.assertEqual([item["template_id"] for item in result["candidates"]], ["template_b", "template_a"])
        self.assertEqual({item["asset_id"] for item in result["candidates"]}, {"template_a", "template_b"})

    def test_rerank_failure_keeps_original_order(self):
        candidates = [
            {"pattern_id": "pattern_a", "similarity_score": 0.8},
            {"pattern_id": "pattern_b", "similarity_score": 0.7},
        ]

        result = rerank_retrieval_candidates(
            candidates,
            query="AHU",
            scorer=FailingScorer(),
            asset_type="system_pattern",
            top_n=10,
        )

        self.assertTrue(result["fallback_used"])
        self.assertEqual([item["pattern_id"] for item in result["candidates"]], ["pattern_a", "pattern_b"])

    def test_agent_does_not_call_reranker_when_switch_is_off(self):
        scorer = FakeScorer([1.0])

        with patch.object(config, "RETRIEVAL_USE_CROSS_ENCODER_RERANK", False), \
             self.agent_runtime() as agent:
            agent.reranker_scorer = scorer
            bundle = agent.retrieve_bundle(
                "fan control",
                similarity_threshold=0.0,
                analysis_result={"retrieval_plan": {"queries": ["fan control"]}, "scenario_analysis": {}},
            )

        self.assertFalse(scorer.called)
        self.assertFalse(bundle["metadata"]["reranker_enabled"])

    def test_agent_reranks_retrieved_subflow_candidates_with_fake_scorer(self):
        scorer = FakeScorer([1.0])

        with patch.object(config, "RETRIEVAL_USE_CROSS_ENCODER_RERANK", True), \
             self.agent_runtime() as agent:
            agent.reranker_scorer = scorer
            bundle = agent.retrieve_bundle(
                "fan control",
                similarity_threshold=0.0,
                analysis_result={"retrieval_plan": {"queries": ["fan control"]}, "scenario_analysis": {}},
            )

        self.assertTrue(scorer.called)
        self.assertTrue(bundle["metadata"]["reranker_enabled"])
        self.assertFalse(bundle["metadata"]["reranker_fallback_used"])
        self.assertEqual(bundle["metadata"]["top_subflow_template_ids"], ["fan_template"])


if __name__ == "__main__":
    unittest.main()
