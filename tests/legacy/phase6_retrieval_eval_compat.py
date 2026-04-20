from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.retrieval_bundle_utils import build_legacy_retrieval_context


class Phase6RetrievalEvalCompatTests(unittest.TestCase):
    def test_legacy_context_stays_compatible_with_phase6_metadata(self):
        bundle = {
            "atomic_modules": [{"module_type": "constInput"}],
            "subflow_templates": [],
            "system_patterns": [],
            "style_guides": [],
            "metadata": {
                "query_text": "fan control",
                "query_variants": ["fan control", "ahu fan control"],
                "retrieved_atomic_count": 1,
                "avg_atomic_score": 0.92,
                "intent": "phase6_eval",
                "detected_operations": [],
                "top_atomic_module_types": ["constInput"],
                "top_atomic_scores": [0.92],
                "top_subflow_template_ids": [],
                "top_subflow_scores": [],
                "top_system_pattern_ids": [],
                "top_system_pattern_scores": [],
            },
        }

        context = build_legacy_retrieval_context(bundle)
        self.assertEqual(context["metadata"]["retrieved_count"], 1)
        self.assertEqual(context["metadata"]["query_variants_used"], 2)
        self.assertEqual(context["metadata"]["intent"], "phase6_eval")


if __name__ == "__main__":
    unittest.main()
