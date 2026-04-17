from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import workflow_trace
from scripts import run_phase6_real_query_suite
from scripts.phase6_shared import CASE_FILE_PATH, load_phase6_cases


def _sample_case_payload() -> dict:
    return {
        "schema_version": "phase6-v1",
        "generated_at": "2026-04-16T18:30:00+08:00",
        "case_owner": "phase6_contract_test",
        "default_trace_policy": "keep_last_failure",
        "cases": [
            {
                "case_id": "golden_case",
                "query": "golden query",
                "case_type": "golden_success",
                "case_source": "contract_test",
                "stable_version": "phase6-batch1",
                "expected_subsystems": ["supply_fan_ctrl"],
                "expected_min_subflow_count": 1,
                "expected_verification_status": "passed",
                "expected_route_decision": "accept",
                "expected_failure_bucket": "passed",
                "allowed_end_states": ["passed"],
                "max_repair_rounds": 0,
                "golden_trace_policy": "keep_always",
                "notes": "contract golden",
                "query_variants": ["golden query", "golden query variant"],
                "expected_template_roles": ["supply_fan_control"],
                "expected_pattern_ids": ["ahu_test_pattern"]
            },
            {
                "case_id": "reject_case",
                "query": "reject query",
                "case_type": "expected_reject",
                "case_source": "contract_test",
                "stable_version": "phase6-batch1",
                "expected_subsystems": ["exhaust_fan_ctrl"],
                "expected_min_subflow_count": 0,
                "expected_verification_status": "retryable_error",
                "expected_route_decision": "reject",
                "expected_failure_bucket": "ambiguous_shared_signal",
                "allowed_end_states": ["rejected_ambiguous_shared_signal"],
                "max_repair_rounds": 1,
                "golden_trace_policy": "keep_last_failure",
                "notes": "contract reject",
                "query_variants": ["reject query"],
                "expected_template_roles": ["exhaust_fan_control"],
                "expected_pattern_ids": ["ahu_test_pattern"]
            },
            {
                "case_id": "repair_case",
                "query": "repair query",
                "case_type": "expected_repair",
                "case_source": "contract_test",
                "stable_version": "phase6-batch1",
                "expected_subsystems": ["supply_fan_ctrl"],
                "expected_min_subflow_count": 1,
                "expected_verification_status": "passed",
                "expected_route_decision": "accept",
                "expected_failure_bucket": "repair_then_passed",
                "allowed_end_states": ["passed", "passed_after_repair"],
                "max_repair_rounds": 1,
                "golden_trace_policy": "keep_last_green",
                "notes": "contract repair direct pass",
                "query_variants": ["repair query"],
                "expected_template_roles": ["supply_fan_control"],
                "expected_pattern_ids": ["ahu_test_pattern"]
            }
        ]
    }


class Phase6RealQuerySuiteContractTests(unittest.TestCase):
    def test_repo_case_file_loads_and_has_required_volume(self):
        payload, cases = load_phase6_cases()
        self.assertEqual(Path(CASE_FILE_PATH).resolve(), CASE_FILE_PATH.resolve())
        self.assertEqual(payload["schema_version"], "phase6-v1")
        self.assertGreaterEqual(len(cases), 12)
        self.assertGreaterEqual(
            sum(1 for case in cases if case.case_type == "golden_success"),
            6,
        )

    def test_invalid_case_values_fail_fast(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            scenarios = [
                ("case_type", "cases", 0, "case_type", "illegal_case_type"),
                ("golden_trace_policy", "cases", 0, "golden_trace_policy", "illegal_policy"),
                ("allowed_end_states", "cases", 1, "allowed_end_states", ["illegal_end_state"]),
            ]
            for name, _, case_index, field_name, value in scenarios:
                payload = _sample_case_payload()
                payload["cases"][case_index][field_name] = value
                case_file = temp_root / f"{name}.json"
                case_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                with self.subTest(name=name), self.assertRaises(ValueError):
                    load_phase6_cases(case_file)

    def test_run_suite_writes_summary_and_required_paths(self):
        payload = _sample_case_payload()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            case_file = temp_root / "cases.json"
            case_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

            def fake_workflow_runner(query: str) -> dict:
                trace_root = Path(workflow_trace.TRACE_OUTPUT_ROOT)
                trace_root.mkdir(parents=True, exist_ok=True)
                trace_dir = trace_root / f"workflow_trace_{query.replace(' ', '_')}"
                trace_dir.mkdir(parents=True, exist_ok=True)

                if query == "golden query":
                    summary = {
                        "workflow_status": "passed",
                        "verification_status": "passed",
                        "repair_round_count": 0,
                        "repair_reject_category": "",
                        "failure_bucket": "passed",
                        "selected_case_pattern_id": "ahu_test_pattern",
                        "retrieved_atomic_count": 1,
                        "retrieved_subflow_count": 1,
                        "retrieved_pattern_count": 1,
                        "top_subflow_template_ids": ["fan_template"],
                        "top_system_pattern_ids": ["ahu_test_pattern"],
                        "subsystem_ids": ["supply_fan_ctrl"],
                        "unresolved_item_types": [],
                    }
                    result = {
                        "verification_report": {"status": "passed", "repair_scope": ""},
                        "route_decision": {"decision": "accept"},
                        "repair_history": [],
                        "retrieval_bundle": {"metadata": {"retrieved_subflow_count": 1}},
                        "subsystem_plan_map": {"supply_fan_ctrl": {"implementation_mode": "reuse_template"}},
                    }
                elif query == "reject query":
                    summary = {
                        "workflow_status": "retryable_error",
                        "verification_status": "retryable_error",
                        "repair_round_count": 1,
                        "repair_reject_category": "ambiguous_shared_signal",
                        "failure_bucket": "ambiguous_shared_signal",
                        "selected_case_pattern_id": "ahu_test_pattern",
                        "retrieved_atomic_count": 1,
                        "retrieved_subflow_count": 0,
                        "retrieved_pattern_count": 1,
                        "top_subflow_template_ids": [],
                        "top_system_pattern_ids": ["ahu_test_pattern"],
                        "subsystem_ids": ["exhaust_fan_ctrl"],
                        "unresolved_item_types": ["ambiguous_shared_signal"],
                    }
                    result = {
                        "verification_report": {"status": "retryable_error", "repair_scope": "planning"},
                        "route_decision": {"decision": "reject", "reason": "ambiguous_shared_signal_unresolved"},
                        "repair_history": [{"scope": "planning"}],
                        "retrieval_bundle": {"metadata": {"retrieved_subflow_count": 0}},
                        "subsystem_plan_map": {"exhaust_fan_ctrl": {"implementation_mode": "atomic_assembly"}},
                    }
                else:
                    summary = {
                        "workflow_status": "passed",
                        "verification_status": "passed",
                        "repair_round_count": 0,
                        "repair_reject_category": "",
                        "failure_bucket": "passed",
                        "selected_case_pattern_id": "ahu_test_pattern",
                        "retrieved_atomic_count": 2,
                        "retrieved_subflow_count": 1,
                        "retrieved_pattern_count": 1,
                        "top_subflow_template_ids": ["fan_template"],
                        "top_system_pattern_ids": ["ahu_test_pattern"],
                        "subsystem_ids": ["supply_fan_ctrl"],
                        "unresolved_item_types": [],
                    }
                    result = {
                        "verification_report": {"status": "passed", "repair_scope": "none"},
                        "route_decision": {"decision": "accept"},
                        "repair_history": [],
                        "retrieval_bundle": {"metadata": {"retrieved_subflow_count": 1}},
                        "subsystem_plan_map": {"supply_fan_ctrl": {"implementation_mode": "reuse_template"}},
                    }

                summary_json = trace_dir / "workflow_node_io_record.json"
                summary_md = trace_dir / "workflow_node_io_record.md"
                final_state_json = trace_dir / "final_state.json"
                summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
                summary_md.write_text("# trace", encoding="utf-8")
                final_state_json.write_text("{}", encoding="utf-8")
                result["final_output"] = {
                    "workflow_trace": {
                        "trace_dir": str(trace_dir.resolve()),
                        "summary_json": str(summary_json.resolve()),
                        "summary_md": str(summary_md.resolve()),
                        "final_state_json": str(final_state_json.resolve()),
                    }
                }
                return result

            suite_summary = run_phase6_real_query_suite.run_suite(
                case_file_path=case_file,
                output_root=temp_root / "phase6_suite_outputs",
                workflow_runner=fake_workflow_runner,
            )

            self.assertEqual(suite_summary["case_count"], 3)
            self.assertEqual(suite_summary["passed_count"], 3)
            self.assertTrue(suite_summary["all_passed"])
            self.assertTrue(Path(suite_summary["summary_json"]).exists())
            self.assertTrue(Path(suite_summary["summary_md"]).exists())
            self.assertTrue(Path(suite_summary["run_dir"]).exists())
            self.assertEqual(suite_summary["expectation_diagnosis_counts"]["expected_repair_but_direct_pass"], 1)
            self.assertEqual(suite_summary["rebaseline_candidate_case_ids"], ["repair_case"])

            on_disk = json.loads(Path(suite_summary["summary_json"]).read_text(encoding="utf-8"))
            self.assertEqual(on_disk["summary_json"], suite_summary["summary_json"])
            self.assertEqual(on_disk["summary_md"], suite_summary["summary_md"])
            self.assertEqual(on_disk["run_dir"], suite_summary["run_dir"])
            self.assertEqual(on_disk["failure_bucket_counts"]["passed"], 2)
            self.assertEqual(on_disk["failure_bucket_counts"]["ambiguous_shared_signal"], 1)
            self.assertEqual(on_disk["expectation_diagnosis_counts"]["matched_expectation"], 2)
            self.assertEqual(on_disk["drift_case_ids"], ["repair_case"])


if __name__ == "__main__":
    unittest.main()
