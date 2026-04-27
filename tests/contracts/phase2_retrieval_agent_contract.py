from __future__ import annotations

import unittest

from tests.retrieval_agent_phase2_shared import (
    RetrievalAgentPhase2ChromaHarness,
    analysis_result,
    safe_console_text,
)


class RetrievalAgentPhase2ContractTests(RetrievalAgentPhase2ChromaHarness):
    def test_retrieve_bundle_reads_temp_chroma_phase2_collections(self) -> None:
        with self.agent_runtime() as agent:
            bundle = agent.retrieve_bundle(
                "fan control",
                similarity_threshold=0.0,
                analysis_result=analysis_result(),
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

    def test_call_updates_state_with_real_temp_bundle(self) -> None:
        with self.agent_runtime() as agent:
            state = {
                "user_query": "fan control",
                "analysis_result": analysis_result(),
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
        self.assertNotIn("retrieval_context", result)

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
