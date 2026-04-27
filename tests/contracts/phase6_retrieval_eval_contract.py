from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import phase6_shared, run_phase6_retrieval_eval


def _sample_case_payload() -> dict:
    return {
        "schema_version": "phase6-v1",
        "generated_at": "2026-04-16T18:30:00+08:00",
        "case_owner": "phase6_eval_contract_test",
        "default_trace_policy": "keep_last_failure",
        "cases": [
            {
                "case_id": "healthy_case",
                "query": "healthy query",
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
                "notes": "healthy retrieval",
                "query_variants": ["healthy query", "healthy query variant"],
                "expected_template_roles": ["supply_fan_control"],
                "expected_pattern_ids": ["ahu__control_dx_status_io_comm_timing__dx_fault_exhaust_fan__v1"],
            },
            {
                "case_id": "asset_gap_case",
                "query": "asset gap query",
                "case_type": "expected_reject",
                "case_source": "contract_test",
                "stable_version": "phase6-batch1",
                "expected_subsystems": ["exhaust_fan_ctrl"],
                "expected_min_subflow_count": 0,
                "expected_verification_status": "retryable_error",
                "expected_route_decision": "reject",
                "expected_failure_bucket": "missing_placeholder_source",
                "allowed_end_states": ["rejected_missing_placeholder_source"],
                "max_repair_rounds": 1,
                "golden_trace_policy": "keep_last_failure",
                "notes": "asset gap retrieval",
                "query_variants": ["asset gap query"],
                "expected_template_roles": ["exhaust_fan_control"],
                "expected_pattern_ids": ["ahu__control_dx_status_io_comm_timing__dx_fault_exhaust_fan__v1"],
            },
        ],
    }


def _contract_pattern_library_assets() -> tuple[list[dict], list[dict], dict]:
    return (
        [
            {
                "template_id": "fan_template",
                "template_role": "supply_fan_control",
                "template_name": "末端组空送风机标准控制",
            }
        ],
        [
            {
                "pattern_id": "ahu__control_dx_status_io_comm_timing__dx_fault_exhaust_fan__v1",
                "required_pages": [
                    {"page_key": "control", "label": "控制"},
                    {"page_key": "io_comm", "label": "IO/通讯"},
                    {"page_key": "timing", "label": "定时"},
                ],
                "optional_pages": [
                    {"page_key": "exhaust_fan", "label": "排风机"},
                    {"page_key": "dx_fault", "label": "直膨机故障"},
                ],
            }
        ],
        {
            "flows_dir": "AHU程序",
            "pattern_library_dir": "AHU程序/pattern_library",
        },
    )


class Phase6RetrievalEvalContractTests(unittest.TestCase):
    def test_run_eval_writes_summary_and_diagnosis(self):
        payload = _sample_case_payload()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            case_file = temp_root / "cases.json"
            case_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

            def fake_bundle_runner(query: str, analysis_result: dict) -> dict:
                query_variants = (analysis_result.get("retrieval_plan", {}) or {}).get("queries", []) or []
                if query == "healthy query":
                    return {
                        "atomic_modules": [{"module_type": "constInput", "similarity_score": 0.95}],
                        "subflow_templates": [
                            {
                                "template_id": "fan_template",
                                "template_role": "supply_fan_control",
                                "similarity_score": 0.93,
                            }
                        ],
                        "system_patterns": [
                            {
                                "pattern_id": "ahu__control_dx_status_io_comm_timing__dx_fault_exhaust_fan__v1",
                                "similarity_score": 0.9,
                            }
                        ],
                        "style_guides": [],
                        "metadata": {
                            "query_variants": query_variants,
                            "top_atomic_module_types": ["constInput"],
                            "top_atomic_scores": [0.95],
                            "top_subflow_template_ids": ["fan_template"],
                            "top_subflow_scores": [0.93],
                            "top_system_pattern_ids": ["ahu__control_dx_status_io_comm_timing__dx_fault_exhaust_fan__v1"],
                            "top_system_pattern_scores": [0.9],
                        },
                    }
                return {
                    "atomic_modules": [{"module_type": "constInput", "similarity_score": 0.88}],
                    "subflow_templates": [],
                    "system_patterns": [
                        {
                            "pattern_id": "ahu__control_dx_status_io_comm_timing__dx_fault_exhaust_fan__v1",
                            "similarity_score": 0.84,
                        }
                    ],
                    "style_guides": [],
                    "metadata": {
                        "query_variants": query_variants,
                        "top_atomic_module_types": ["constInput"],
                        "top_atomic_scores": [0.88],
                        "top_subflow_template_ids": [],
                        "top_subflow_scores": [],
                        "top_system_pattern_ids": ["ahu__control_dx_status_io_comm_timing__dx_fault_exhaust_fan__v1"],
                        "top_system_pattern_scores": [0.84],
                    },
                }

            with patch.object(
                run_phase6_retrieval_eval,
                "load_pattern_library_assets",
                return_value=_contract_pattern_library_assets(),
            ), patch.object(
                phase6_shared,
                "load_pattern_library_assets",
                return_value=_contract_pattern_library_assets(),
            ):
                summary = run_phase6_retrieval_eval.run_eval(
                    case_file_path=case_file,
                    output_root=temp_root / "phase6_eval_outputs",
                    bundle_runner=fake_bundle_runner,
                )

            self.assertEqual(summary["case_count"], 2)
            self.assertTrue(Path(summary["summary_json"]).exists())
            self.assertTrue(Path(summary["summary_md"]).exists())
            self.assertTrue(Path(summary["run_dir"]).exists())
            self.assertEqual(summary["diagnosis_counts"]["healthy"], 1)
            self.assertEqual(summary["diagnosis_counts"]["asset_gap"], 1)
            self.assertEqual(summary["diagnosis_case_ids"]["asset_gap"], ["asset_gap_case"])
            self.assertEqual(summary["template_asset_gap_case_ids"], ["asset_gap_case"])
            self.assertEqual(summary["pattern_asset_gap_case_ids"], [])
            self.assertEqual(summary["asset_gap_template_role_counts"], {"exhaust_fan_control": 1})
            self.assertEqual(
                summary["asset_gap_template_role_case_ids"]["exhaust_fan_control"],
                ["asset_gap_case"],
            )
            self.assertEqual(summary["asset_gap_pattern_id_counts"], {})
            self.assertEqual(summary["asset_gap_case_type_counts"], {"expected_reject": 1})
            self.assertTrue(summary["single_root_asset_gap"]["is_single_root_cause"])
            self.assertEqual(summary["single_root_asset_gap"]["template_role"], "exhaust_fan_control")
            self.assertTrue(summary["ready_for_c"])
            self.assertEqual(
                summary["ready_for_c_reason"],
                "golden_retrieval_stable_with_single_known_nonblocking_asset_backlog",
            )
            self.assertEqual(summary["preferred_next_step"], "continue_ab_diagnostic_closure")
            self.assertEqual(summary["ready_for_c_blockers"], [])

            results_by_case = {item["case_id"]: item for item in summary["results"]}
            self.assertEqual(results_by_case["healthy_case"]["retrieval_diagnosis"], "healthy")
            self.assertTrue(results_by_case["healthy_case"]["target_template_hit_top5"])
            self.assertEqual(results_by_case["asset_gap_case"]["retrieval_diagnosis"], "asset_gap")
            self.assertEqual(results_by_case["asset_gap_case"]["missing_template_roles"], ["exhaust_fan_control"])
            self.assertEqual(results_by_case["asset_gap_case"]["missing_pattern_ids"], [])
            self.assertEqual(results_by_case["asset_gap_case"]["asset_gap_reason"], "missing_template_assets")
            self.assertEqual(
                results_by_case["asset_gap_case"]["asset_gap_root_cause"],
                "source_context_with_adjacent_non_role_subflow",
            )
            self.assertIn(
                "exhaust_fan",
                results_by_case["asset_gap_case"]["asset_gap_source_pattern_page_keys"],
            )
            self.assertTrue(results_by_case["asset_gap_case"]["asset_gap_source_flow_paths"])
            self.assertTrue(
                results_by_case["asset_gap_case"]["missing_template_role_diagnostics"][0][
                    "adjacent_subflow_definition_names"
                ]
            )

            on_disk = json.loads(Path(summary["summary_json"]).read_text(encoding="utf-8"))
            self.assertEqual(on_disk["summary_json"], summary["summary_json"])
            self.assertEqual(on_disk["summary_md"], summary["summary_md"])
            self.assertEqual(on_disk["run_dir"], summary["run_dir"])
            self.assertEqual(on_disk["diagnosis_case_ids"]["healthy"], ["healthy_case"])
            self.assertEqual(on_disk["ready_for_c"], summary["ready_for_c"])
            self.assertEqual(
                on_disk["asset_gap_template_role_counts"],
                summary["asset_gap_template_role_counts"],
            )

    def test_ready_for_c_turns_false_when_golden_case_has_asset_gap(self):
        payload = {
            "schema_version": "phase6-v1",
            "generated_at": "2026-04-16T18:30:00+08:00",
            "case_owner": "phase6_eval_contract_test",
            "default_trace_policy": "keep_last_failure",
            "cases": [
                {
                    "case_id": "golden_asset_gap_case",
                    "query": "golden exhaust query",
                    "case_type": "golden_success",
                    "case_source": "contract_test",
                    "stable_version": "phase6-batch1",
                    "expected_subsystems": ["exhaust_fan_ctrl"],
                    "expected_min_subflow_count": 0,
                    "expected_verification_status": "passed",
                    "expected_route_decision": "accept",
                    "expected_failure_bucket": "passed",
                    "allowed_end_states": ["passed"],
                    "max_repair_rounds": 0,
                    "golden_trace_policy": "keep_always",
                    "notes": "golden asset gap",
                    "query_variants": ["golden exhaust query"],
                    "expected_template_roles": ["exhaust_fan_control"],
                    "expected_pattern_ids": ["ahu__control_dx_status_io_comm_timing__dx_fault_exhaust_fan__v1"],
                }
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            case_file = temp_root / "cases.json"
            case_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

            def fake_bundle_runner(query: str, analysis_result: dict) -> dict:
                del query, analysis_result
                return {
                    "atomic_modules": [{"module_type": "constInput", "similarity_score": 0.88}],
                    "subflow_templates": [],
                    "system_patterns": [
                        {
                            "pattern_id": "ahu__control_dx_status_io_comm_timing__dx_fault_exhaust_fan__v1",
                            "similarity_score": 0.84,
                        }
                    ],
                    "style_guides": [],
                    "metadata": {
                        "query_variants": ["golden exhaust query"],
                        "top_atomic_module_types": ["constInput"],
                        "top_atomic_scores": [0.88],
                        "top_subflow_template_ids": [],
                        "top_subflow_scores": [],
                        "top_system_pattern_ids": ["ahu__control_dx_status_io_comm_timing__dx_fault_exhaust_fan__v1"],
                        "top_system_pattern_scores": [0.84],
                    },
                }

            with patch.object(
                run_phase6_retrieval_eval,
                "load_pattern_library_assets",
                return_value=_contract_pattern_library_assets(),
            ), patch.object(
                phase6_shared,
                "load_pattern_library_assets",
                return_value=_contract_pattern_library_assets(),
            ):
                summary = run_phase6_retrieval_eval.run_eval(
                    case_file_path=case_file,
                    output_root=temp_root / "phase6_eval_outputs",
                    bundle_runner=fake_bundle_runner,
                )

            self.assertFalse(summary["ready_for_c"])
            self.assertIn("golden_asset_gap_present", summary["ready_for_c_blockers"])
            self.assertEqual(
                summary["ready_for_c_reason"],
                "retrieval_gates_not_met_for_work_package_c",
            )


if __name__ == "__main__":
    unittest.main()
