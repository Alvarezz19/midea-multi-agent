from __future__ import annotations

import unittest

from tests.retrieval_agent_phase2_shared import (
    RetrievalAgentPhase2ChromaHarness,
    analysis_result,
)


class RetrievalAgentPhase2CompatTests(RetrievalAgentPhase2ChromaHarness):
    def test_retrieve_returns_legacy_atomic_view_only(self) -> None:
        with self.agent_runtime() as agent:
            context = agent.retrieve(
                "fan control",
                similarity_threshold=0.0,
                analysis_result=analysis_result(),
            )

        self.assertEqual(
            [node["module_type"] for node in context["relevant_nodes"]],
            ["constInput"],
        )
        self.assertEqual(context["metadata"]["retrieved_count"], 1)
        self.assertEqual(context["metadata"]["intent"], "general_query")


if __name__ == "__main__":
    unittest.main()
