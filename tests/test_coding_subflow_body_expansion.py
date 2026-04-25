from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.coding_agent import CodingAgent
from agents.repair_router import RepairRouter
from agents.verifier_agent import VerifierAgent
from utils.knowledge_contract_loader import find_subflow_template_contract
from utils.platform_flow_schema import validate_flow_document


def _load_supply_fan_template() -> dict:
    template = find_subflow_template_contract(
        template_role="supply_fan_control",
        name_contains="末端组空送风机标准控制",
    )
    if not template:
        raise AssertionError("未找到末端组空送风机标准控制模板。")
    return template


def _port_irs(ports: list[dict]) -> list[dict]:
    return [
        {
            "port_index": index,
            "name": str(port.get("name", "")),
            "x": int(port.get("x", 0) or 0),
            "y": int(port.get("y", 0) or 0),
        }
        for index, port in enumerate(ports)
    ]


def _make_graph_ir(template: dict) -> dict:
    template_json = copy.deepcopy(template["template_json"])
    template_id = template["template_id"]
    definition_id = template["definition_id"]
    return {
        "graph_ir_version": "2.0",
        "goal": "送风机标准控制 body 编译测试",
        "pages": [{"page_id": "page_control", "label": "控制", "kind": "control", "order": 0}],
        "subflow_definitions": [
            {
                "template_id": template_id,
                "definition_id": definition_id,
                "name": template["template_name"],
                "inputs": int(template_json.get("inputs", len(template_json.get("in", []) or [])) or 0),
                "outputs": int(template_json.get("outputs", len(template_json.get("out", []) or [])) or 0),
                "in_ports": _port_irs(template_json.get("in", []) or []),
                "out_ports": _port_irs(template_json.get("out", []) or []),
                "template_source": "test_fixture",
                "raw_definition": template_json,
                "internal_flow_objects": copy.deepcopy(template["internal_flow_objects"]),
            }
        ],
        "node_instances": [
            {
                "instance_id": "node::supply_fan_ctrl::main",
                "logic_id": "main",
                "module_type": template_id,
                "page_id": "page_control",
                "subflow_id": None,
                "template_id": template_id,
                "parameters": {"name": "送风机标准控制"},
                "position": {"x": 200, "y": 120},
                "input_count": 0,
                "output_count": int(template_json.get("outputs", 0) or 0),
                "reasoning": "body expansion test",
            }
        ],
        "edges": [],
        "signal_registry": [],
        "layout_hints": {},
        "unresolved_items": [],
    }


def _compile_supply_fan_template() -> tuple[dict, dict]:
    template = _load_supply_fan_template()
    graph_ir = _make_graph_ir(template)
    retrieval_bundle = {
        "atomic_modules": [],
        "subflow_templates": [template],
        "system_patterns": [],
        "style_guides": [],
        "metadata": {},
    }
    return template, CodingAgent().compile_graph_from_bundle(graph_ir, retrieval_bundle)


def _compile_supply_fan_graph() -> tuple[dict, dict, dict]:
    template = _load_supply_fan_template()
    graph_ir = _make_graph_ir(template)
    retrieval_bundle = {
        "atomic_modules": [],
        "subflow_templates": [template],
        "system_patterns": [],
        "style_guides": [],
        "metadata": {},
    }
    artifact = CodingAgent().compile_graph_from_bundle(graph_ir, retrieval_bundle)
    return template, graph_ir, artifact


class CodingSubflowBodyExpansionTests(unittest.TestCase):
    def test_fixture_supply_fan_template_has_internal_body(self):
        template = _load_supply_fan_template()
        template_json = template["template_json"]

        self.assertEqual(template["template_role"], "supply_fan_control")
        self.assertEqual(template["template_name"], "末端组空送风机标准控制")
        self.assertGreaterEqual(len(template["internal_flow_objects"]), 35)
        self.assertEqual(len(template_json["in"]), 9)
        self.assertEqual(len(template_json["out"]), 4)

    def test_compile_subflow_definition_expands_internal_body(self):
        template, artifact = _compile_supply_fan_template()
        report = artifact["compile_report"]

        self.assertEqual(report["subflow_count"], 1)
        self.assertEqual(report["page_count"], 1)
        self.assertGreaterEqual(report["body_node_count"], 35)
        self.assertEqual(report["body_node_count"], len(template["internal_flow_objects"]))
        self.assertEqual(report["body_expansion_errors"], [])

        object_types = {obj["type"] for obj in artifact["flow_objects"]}
        self.assertIn("tab", object_types)
        self.assertIn("subflow", object_types)
        self.assertTrue(any(str(obj["type"]).startswith("subflow:") for obj in artifact["flow_objects"]))

    def test_subflow_body_ids_are_remapped(self):
        template, artifact = _compile_supply_fan_template()
        raw_body_ids = {str(obj["id"]) for obj in template["internal_flow_objects"]}
        real_body_ids = {
            str(obj["id"])
            for obj in artifact["flow_objects"]
            if str(obj.get("z", "")) == next(item["id"] for item in artifact["flow_objects"] if item["type"] == "subflow")
        }

        self.assertTrue(real_body_ids)
        self.assertFalse(raw_body_ids & real_body_ids)
        first_raw_id = str(template["internal_flow_objects"][0]["id"])
        self.assertIn(f"body::{template['definition_id']}::{first_raw_id}", artifact["id_map"])

    def test_subflow_body_z_points_to_real_subflow_id(self):
        _, artifact = _compile_supply_fan_template()
        subflow_id = next(item["id"] for item in artifact["flow_objects"] if item["type"] == "subflow")
        body_objects = [obj for obj in artifact["flow_objects"] if obj.get("z") == subflow_id]

        self.assertTrue(body_objects)
        self.assertTrue(all(obj["z"] == subflow_id for obj in body_objects))

    def test_subflow_definition_in_out_wires_are_remapped(self):
        _, artifact = _compile_supply_fan_template()
        subflow = next(item for item in artifact["flow_objects"] if item["type"] == "subflow")
        body_ids = {obj["id"] for obj in artifact["flow_objects"] if obj.get("z") == subflow["id"]}

        in_out_targets = [
            target["id"]
            for field_name in ("in", "out")
            for port in subflow[field_name]
            for target in port.get("wires", [])
        ]

        self.assertTrue(in_out_targets)
        self.assertTrue(set(in_out_targets).issubset(body_ids))

    def test_subflow_body_wire_targets_are_valid(self):
        _, artifact = _compile_supply_fan_template()
        object_ids = {obj["id"] for obj in artifact["flow_objects"]}
        subflow_id = next(item["id"] for item in artifact["flow_objects"] if item["type"] == "subflow")
        body_objects = [obj for obj in artifact["flow_objects"] if obj.get("z") == subflow_id]

        for obj in body_objects:
            for output_group in obj.get("wires", []):
                for target in output_group:
                    self.assertIn(target["id"], object_ids)

        report = validate_flow_document(artifact["flow_objects"])
        self.assertEqual(report["status"], "passed", report["issues"][:3])

    def test_subflow_body_compilation_is_stable(self):
        _, first = _compile_supply_fan_template()
        _, second = _compile_supply_fan_template()

        self.assertEqual(json.loads(first["json_text"]), json.loads(second["json_text"]))
        self.assertEqual(first["id_map"], second["id_map"])

    def test_verifier_accepts_normal_body_expansion_result(self):
        _, graph_ir, artifact = _compile_supply_fan_graph()

        report = VerifierAgent().verify(graph_ir, artifact)

        self.assertEqual(report["status"], "passed", report["issues"][:3])
        self.assertEqual(report["repair_scope"], "none")

    def test_verifier_rejects_deleted_body_nodes(self):
        _, graph_ir, artifact = _compile_supply_fan_graph()
        subflow_id = next(obj["id"] for obj in artifact["flow_objects"] if obj["type"] == "subflow")
        artifact["flow_objects"] = [obj for obj in artifact["flow_objects"] if obj.get("z") != subflow_id]
        artifact["json_text"] = json.dumps(artifact["flow_objects"], ensure_ascii=False)

        report = VerifierAgent().verify(graph_ir, artifact)
        route = RepairRouter().route(report, enable_repair_agent=False)

        self.assertEqual(report["status"], "retryable_error")
        self.assertEqual(report["repair_scope"], "compile")
        self.assertTrue(any(issue["rule_id"] == "compile.subflow.body.must_exist" for issue in report["issues"]))
        self.assertEqual(route["decision"], "reject")
        self.assertEqual(route["reason"], "repair_agent_disabled")

    def test_verifier_rejects_broken_body_wire_target(self):
        _, graph_ir, artifact = _compile_supply_fan_graph()
        subflow_id = next(obj["id"] for obj in artifact["flow_objects"] if obj["type"] == "subflow")
        body_node = next(
            obj
            for obj in artifact["flow_objects"]
            if obj.get("z") == subflow_id and any(group for group in obj.get("wires", []))
        )
        body_node["wires"][0][0]["id"] = "missing_target"
        artifact["json_text"] = json.dumps(artifact["flow_objects"], ensure_ascii=False)

        report = VerifierAgent().verify(graph_ir, artifact)

        self.assertEqual(report["status"], "retryable_error")
        self.assertEqual(report["repair_scope"], "compile")
        self.assertTrue(
            any(issue["rule_id"] in {"compile.wire.target.must_exist", "flow.wire.target.must_exist"} for issue in report["issues"])
        )

    def test_verifier_rejects_broken_subflow_instance_reference(self):
        _, graph_ir, artifact = _compile_supply_fan_graph()
        instance = next(obj for obj in artifact["flow_objects"] if str(obj["type"]).startswith("subflow:"))
        instance["type"] = "subflow:missing_definition"
        artifact["json_text"] = json.dumps(artifact["flow_objects"], ensure_ascii=False)

        report = VerifierAgent().verify(graph_ir, artifact)

        self.assertEqual(report["status"], "retryable_error")
        self.assertEqual(report["repair_scope"], "compile")
        self.assertTrue(
            any(issue["rule_id"] == "compile.subflow.instance.definition.must_exist" for issue in report["issues"])
        )

    def test_verifier_rejects_strict_compile_report_errors(self):
        _, graph_ir, artifact = _compile_supply_fan_graph()
        artifact["compile_report"]["dropped_node_count"] = 1
        artifact["compile_report"]["unresolved_placeholder_count"] = 1

        report = VerifierAgent().verify(graph_ir, artifact)

        self.assertEqual(report["status"], "retryable_error")
        self.assertEqual(report["repair_scope"], "compile")
        self.assertTrue(
            any(issue["rule_id"] == "compile.report.strict_errors.must_be_empty" for issue in report["issues"])
        )


if __name__ == "__main__":
    unittest.main()
