from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.assembly_agent import AssemblyAgent
from agents.legacy.assembly_agent import AssemblyAgent as LegacyAssemblyAgent
from agents.debugging_agent import DebuggingAgent
from agents.legacy.debugging_agent import DebuggingAgent as LegacyDebuggingAgent
from agents.legacy.planning_agent import (
    LLMManager as LegacyPlanningLLMManager,
    PlanConnection as LegacyPlanConnection,
    PlanIR as LegacyPlanIR,
    PlanNode as LegacyPlanNode,
    PlanningAgent as LegacyPlanningAgent,
)
from agents.legacy.retrieval_agent_old import RetrievalAgent as LegacyRetrievalAgent
from agents.legacy.validation_agent import ValidationAgent as LegacyValidationAgent
from agents.planning_agent import LLMManager, PlanConnection, PlanIR, PlanNode, PlanningAgent
from agents.retrieval_agent_old import RetrievalAgent
from agents.validation_agent import ValidationAgent


class LegacyAgentImportTests(unittest.TestCase):
    def test_assembly_agent_wrapper_reexports_legacy_class(self):
        self.assertIs(AssemblyAgent, LegacyAssemblyAgent)

    def test_validation_agent_wrapper_reexports_legacy_class(self):
        self.assertIs(ValidationAgent, LegacyValidationAgent)

    def test_debugging_agent_wrapper_reexports_legacy_class(self):
        self.assertIs(DebuggingAgent, LegacyDebuggingAgent)

    def test_planning_agent_wrapper_reexports_legacy_symbols(self):
        self.assertIs(PlanningAgent, LegacyPlanningAgent)
        self.assertIs(PlanConnection, LegacyPlanConnection)
        self.assertIs(PlanIR, LegacyPlanIR)
        self.assertIs(PlanNode, LegacyPlanNode)
        self.assertIs(LLMManager, LegacyPlanningLLMManager)

    def test_retrieval_agent_old_wrapper_reexports_legacy_class(self):
        self.assertIs(RetrievalAgent, LegacyRetrievalAgent)


if __name__ == "__main__":
    unittest.main()
