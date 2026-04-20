from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.debugging_agent import DebuggingAgent
from agents.legacy.debugging_agent import DebuggingAgent as LegacyDebuggingAgent
from agents.legacy.retrieval_agent_old import RetrievalAgent as LegacyRetrievalAgent
from agents.legacy.validation_agent import ValidationAgent as LegacyValidationAgent
from agents.retrieval_agent_old import RetrievalAgent
from agents.validation_agent import ValidationAgent


class LegacyAgentImportTests(unittest.TestCase):
    def test_validation_agent_wrapper_reexports_legacy_class(self):
        self.assertIs(ValidationAgent, LegacyValidationAgent)

    def test_debugging_agent_wrapper_reexports_legacy_class(self):
        self.assertIs(DebuggingAgent, LegacyDebuggingAgent)

    def test_retrieval_agent_old_wrapper_reexports_legacy_class(self):
        self.assertIs(RetrievalAgent, LegacyRetrievalAgent)


if __name__ == "__main__":
    unittest.main()
