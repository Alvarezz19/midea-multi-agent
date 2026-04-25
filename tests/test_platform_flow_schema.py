from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.platform_flow_schema import validate_flow_document


REAL_FLOW_FILES = [
    PROJECT_ROOT / "AHU程序" / "flows_20251210190941.json",
    PROJECT_ROOT / "AHU程序" / "flows_20251229175702.json",
    PROJECT_ROOT / "AHU程序" / "flows_20260206160555.json",
]


def _minimal_valid_flow() -> list[dict]:
    return [
        {"id": "tab1", "type": "tab", "label": "控制", "disabled": False, "info": ""},
        {
            "id": "sub1",
            "type": "subflow",
            "name": "子流程",
            "in": [{"x": 0, "y": 0, "name": "输入", "wires": [{"id": "body1", "port": 0}]}],
            "out": [{"x": 100, "y": 0, "name": "输出", "wires": [{"id": "body1", "port": 0}]}],
            "inputs": 1,
            "outputs": 1,
        },
        {"id": "body1", "type": "constInput", "z": "sub1", "inputs": 0, "outputs": 1, "wires": [[]]},
        {"id": "inst1", "type": "subflow:sub1", "z": "tab1", "inputs": 1, "outputs": 1, "wires": [[]]},
    ]


class PlatformFlowSchemaTests(unittest.TestCase):
    def test_real_ahu_flow_files_pass_minimal_platform_schema(self):
        for path in REAL_FLOW_FILES:
            with self.subTest(path=path.name):
                flow_objects = json.loads(path.read_text(encoding="utf-8"))
                report = validate_flow_document(flow_objects)

                self.assertEqual(report["status"], "passed", report["issues"][:3])
                self.assertGreater(report["metrics"]["object_count"], 900)
                self.assertGreater(report["metrics"]["body_node_count"], 0)

    def test_negative_duplicate_id_fails(self):
        flow = _minimal_valid_flow()
        flow[-1]["id"] = "body1"

        report = validate_flow_document(flow)

        self.assertEqual(report["status"], "failed")
        self.assertTrue(any(issue["rule_id"] == "flow.object.id.unique" for issue in report["issues"]))

    def test_negative_missing_subflow_definition_fails(self):
        flow = _minimal_valid_flow()
        flow[-1]["type"] = "subflow:missing"

        report = validate_flow_document(flow)

        self.assertEqual(report["status"], "failed")
        self.assertTrue(
            any(issue["rule_id"] == "compile.subflow.instance.definition.must_exist" for issue in report["issues"])
        )

    def test_negative_missing_parent_and_wire_target_fail(self):
        flow = _minimal_valid_flow()
        flow[2]["z"] = "missing_parent"
        flow[2]["wires"] = [[{"id": "missing_target", "port": 0}]]

        report = validate_flow_document(flow)
        rule_ids = {issue["rule_id"] for issue in report["issues"]}

        self.assertEqual(report["status"], "failed")
        self.assertIn("flow.object.parent.must_exist", rule_ids)
        self.assertIn("flow.wire.target.must_exist", rule_ids)

    def test_negative_wires_must_be_list(self):
        flow = _minimal_valid_flow()
        flow[2]["wires"] = "bad"

        report = validate_flow_document(flow)

        self.assertEqual(report["status"], "failed")
        self.assertTrue(any(issue["rule_id"] == "flow.wires.must_be_list" for issue in report["issues"]))

    def test_negative_schema_contract_enum_range_and_placeholder_fail(self):
        flow = _minimal_valid_flow()
        flow.append({
            "id": "pid1",
            "type": "pid",
            "z": "tab1",
            "inputs": 13,
            "outputs": 1,
            "pidMode": "bad",
            "interval": 0,
            "name": "{{unresolved}}",
            "wires": [[]],
        })

        report = validate_flow_document(flow)
        rule_ids = {issue["rule_id"] for issue in report["issues"]}

        self.assertEqual(report["status"], "failed")
        self.assertIn("flow.contract.parameter.enum", rule_ids)
        self.assertIn("flow.contract.parameter.minimum", rule_ids)
        self.assertIn("flow.contract.parameter.maximum", rule_ids)
        self.assertIn("flow.object.placeholder.must_not_remain", rule_ids)

    def test_negative_subflow_body_rules_fail(self):
        flow = _minimal_valid_flow()
        without_body = [obj for obj in flow if obj["id"] != "body1"]

        report = validate_flow_document(without_body)
        rule_ids = {issue["rule_id"] for issue in report["issues"]}

        self.assertEqual(report["status"], "failed")
        self.assertIn("compile.subflow.body.must_exist", rule_ids)
        self.assertIn("compile.subflow.inout.wire.target.must_exist", rule_ids)

        wrong_parent = copy.deepcopy(flow)
        wrong_parent[2]["z"] = "tab1"
        report = validate_flow_document(wrong_parent)
        self.assertTrue(
            any(issue["rule_id"] == "compile.subflow.inout.wire.target.must_be_body_node" for issue in report["issues"])
        )


if __name__ == "__main__":
    unittest.main()
