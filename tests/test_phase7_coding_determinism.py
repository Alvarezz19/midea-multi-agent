import copy
import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.assembly_agent import AssemblyAgent
from agents.coding_agent import CodingAgent


def make_retrieval_bundle():
    return {
        "atomic_modules": [
            {
                "module_type": "constInput",
                "name": "Constant Input",
                "template_json": {
                    "id": "",
                    "type": "constInput",
                    "z": "",
                    "name": "",
                    "fixedValue": 0,
                    "x": 0,
                    "y": 0,
                    "wires": [],
                    "inputs": 0,
                    "outputs": 1,
                },
                "ports_definition": {
                    "inputs": [],
                    "outputs": [{"label": "out", "condition": "always"}],
                },
                "parameters_schema": {"fixedValue": {"type": "number"}},
            },
            {
                "module_type": "add",
                "name": "Add",
                "template_json": {
                    "id": "",
                    "type": "add",
                    "z": "",
                    "name": "",
                    "x": 0,
                    "y": 0,
                    "wires": [],
                    "inputs": "{{inputCount}}",
                    "outputs": 1,
                },
                "ports_definition": {
                    "inputs": [
                        {"label": "in0", "condition": "always"},
                        {"label": "in1", "condition": "always"},
                    ],
                    "outputs": [{"label": "out", "condition": "always"}],
                },
                "parameters_schema": {"inputCount": {"type": "integer"}},
            },
        ],
        "subflow_templates": [],
        "system_patterns": [],
        "style_guides": [],
        "metadata": {"query_bundle_version": "phase7-test"},
    }


def make_execution_plan():
    return {
        "goal": "sum two constants",
        "nodes": [
            {
                "logic_id": "const_a",
                "module_type": "constInput",
                "parameters": {"fixedValue": 1, "name": "A"},
                "reasoning": "first constant",
            },
            {
                "logic_id": "const_b",
                "module_type": "constInput",
                "parameters": {"fixedValue": 2, "name": "B"},
                "reasoning": "second constant",
            },
            {
                "logic_id": "sum",
                "module_type": "add",
                "parameters": {"inputCount": 2, "name": "SUM"},
                "reasoning": "sum values",
            },
        ],
        "connections": [
            {
                "from_node": "const_a",
                "from_port_index": 0,
                "to_node": "sum",
                "to_port_index": 0,
            },
            {
                "from_node": "const_b",
                "from_port_index": 0,
                "to_node": "sum",
                "to_port_index": 1,
            },
        ],
    }


class CodingDeterminismTests(unittest.TestCase):
    def setUp(self):
        self.bundle = make_retrieval_bundle()
        self.assembly_agent = AssemblyAgent()
        self.coding_agent = CodingAgent()

    def test_compile_graph_is_stable_for_same_inputs(self):
        graph_ir = self.assembly_agent.assemble(make_execution_plan(), self.bundle)

        artifact_first = self.coding_agent.compile_graph(graph_ir, self.bundle)
        artifact_second = self.coding_agent.compile_graph(copy.deepcopy(graph_ir), copy.deepcopy(self.bundle))

        self.assertEqual(artifact_first["id_map"], artifact_second["id_map"])
        self.assertEqual(artifact_first["json_text"], artifact_second["json_text"])
        self.assertEqual(artifact_first["flow_objects"], artifact_second["flow_objects"])

    def test_recompile_after_repair_keeps_existing_entity_ids_stable(self):
        graph_ir = self.assembly_agent.assemble(make_execution_plan(), self.bundle)
        original_artifact = self.coding_agent.compile_graph(graph_ir, self.bundle)

        repaired_graph_ir = copy.deepcopy(graph_ir)
        repaired_node = next(
            node for node in repaired_graph_ir["node_instances"]
            if node["instance_id"] == "node::sum"
        )
        repaired_node["parameters"]["name"] = "SUM_REPAIRED"

        repaired_artifact = self.coding_agent.compile_graph(repaired_graph_ir, self.bundle)

        self.assertEqual(original_artifact["id_map"], repaired_artifact["id_map"])
        self.assertNotEqual(original_artifact["json_text"], repaired_artifact["json_text"])

        original_objects = {
            obj["id"]: obj for obj in json.loads(original_artifact["json_text"])
            if obj.get("type") != "tab"
        }
        repaired_objects = {
            obj["id"]: obj for obj in json.loads(repaired_artifact["json_text"])
            if obj.get("type") != "tab"
        }

        self.assertEqual(set(original_objects), set(repaired_objects))
        self.assertEqual(
            repaired_objects[original_artifact["id_map"]["node::sum"]]["name"],
            "SUM_REPAIRED",
        )


if __name__ == "__main__":
    unittest.main()
