from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class Phase6ReadinessContractTests(unittest.TestCase):
    def test_phase6_readiness_docs_exist_and_cover_required_topics(self):
        expectations = {
            PROJECT_ROOT / "AHU程序" / "Phase6_副作用幂等性清单.md": [
                "副作用幂等性清单",
                "analysis",
                "retrieval",
                "coding",
                "repair_agent",
                "workflow_trace",
            ],
            PROJECT_ROOT / "AHU程序" / "Phase6_thread_id与恢复契约.md": [
                "thread_id",
                "resume",
                "checkpointer",
                "attempt_id",
                "configurable.thread_id",
            ],
            PROJECT_ROOT / "AHU程序" / "Phase6_Send_HITL准入评审表.md": [
                "conditional-go",
                "no-go",
                "subsystem_plan_map",
                "parallel_merge_conflicts",
                "checkpointer",
            ],
        }

        for path, keywords in expectations.items():
            with self.subTest(path=path.name):
                self.assertTrue(path.exists(), f"缺少 readiness 文档: {path}")
                text = path.read_text(encoding="utf-8")
                for keyword in keywords:
                    self.assertIn(keyword, text)

    def test_phase6_readiness_truths_match_current_code_boundary(self):
        workflow_text = (PROJECT_ROOT / "workflow.py").read_text(encoding="utf-8")
        workflow_trace_text = (PROJECT_ROOT / "workflow_trace.py").read_text(encoding="utf-8")
        poc_text = (PROJECT_ROOT / "scripts" / "poc_phase4_hitl.py").read_text(encoding="utf-8")

        self.assertIn("repair_router", workflow_text)
        self.assertIn("repair_agent", workflow_text)
        self.assertIn("populate_phase4_workflow", workflow_trace_text)
        self.assertNotIn("Send(", workflow_text)
        self.assertNotIn("Send(", workflow_trace_text)
        self.assertNotIn("interrupt(", workflow_text)
        self.assertNotIn("interrupt(", workflow_trace_text)
        self.assertIn("compile(checkpointer=InMemorySaver())", poc_text)
        self.assertIn('config = {"configurable": build_configurable_thread(thread_id)}', poc_text)
        self.assertIn("interrupt(", poc_text)
        self.assertIn("Command(resume=", poc_text)


if __name__ == "__main__":
    unittest.main()
