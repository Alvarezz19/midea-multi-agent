import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.assembly_agent import AssemblyAgent
from agents.coding_agent import CodingAgent
from agents.verifier_agent import VerifierAgent
import workflow
import workflow_trace


def make_retrieval_context():
    return {
        "query": "sum two constants",
        "relevant_nodes": [
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
                "parameters_schema": {
                    "fixedValue": {"type": "number"},
                },
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
                "parameters_schema": {
                    "inputCount": {"type": "integer"},
                },
            },
        ],
        "metadata": {
            "retrieved_count": 2,
            "avg_confidence_score": 0.95,
        },
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


class WorkflowPhase1Tests(unittest.TestCase):
    def setUp(self):
        self.retrieval_context = make_retrieval_context()
        self.execution_plan = make_execution_plan()
        self.assembly_agent = AssemblyAgent()
        self.coding_agent = CodingAgent()
        self.verifier_agent = VerifierAgent()

    def test_assembly_builds_minimal_graph_ir(self):
        graph_ir = self.assembly_agent.assemble(self.execution_plan, self.retrieval_context)

        self.assertEqual(graph_ir["graph_ir_version"], "2.0")
        self.assertEqual(len(graph_ir["pages"]), 1)
        self.assertEqual(len(graph_ir["node_instances"]), 3)
        self.assertEqual(len(graph_ir["edges"]), 2)
        self.assertEqual(graph_ir["unresolved_items"], [])

        sum_node = next(node for node in graph_ir["node_instances"] if node["logic_id"] == "sum")
        self.assertEqual(sum_node["input_count"], 2)
        self.assertEqual(sum_node["output_count"], 1)

    def test_compiler_emits_deterministic_artifact(self):
        graph_ir = self.assembly_agent.assemble(self.execution_plan, self.retrieval_context)
        artifact = self.coding_agent.compile_graph(graph_ir, self.retrieval_context)
        artifact_recompiled = self.coding_agent.compile_graph(graph_ir, self.retrieval_context)

        flow_objects = artifact["flow_objects"]
        self.assertEqual(len(flow_objects), 4)
        self.assertEqual(artifact["compile_report"]["page_count"], 1)
        self.assertEqual(artifact["compile_report"]["node_count"], 3)
        self.assertEqual(artifact["compile_report"]["subflow_count"], 0)
        self.assertEqual(artifact["id_map"], artifact_recompiled["id_map"])
        self.assertEqual(artifact["json_text"], artifact_recompiled["json_text"])

        parsed = json.loads(artifact["json_text"])
        self.assertEqual(len(parsed), len(flow_objects))

        sum_real_id = artifact["id_map"]["node::sum"]
        const_a_real_id = artifact["id_map"]["node::const_a"]
        const_b_real_id = artifact["id_map"]["node::const_b"]
        sum_object = next(obj for obj in flow_objects if obj["id"] == sum_real_id)

        self.assertEqual(sum_object["type"], "add")
        self.assertEqual(len(sum_object["wires"]), 2)
        self.assertEqual(sum_object["wires"][0][0]["id"], const_a_real_id)
        self.assertEqual(sum_object["wires"][1][0]["id"], const_b_real_id)

    def test_compiler_supports_subflow_relations(self):
        graph_ir = {
            "graph_ir_version": "2.0",
            "goal": "subflow smoke test",
            "pages": [
                {"page_id": "page_control", "label": "Control", "kind": "control", "order": 0},
            ],
            "subflow_definitions": [
                {
                    "template_id": "fan_template",
                    "definition_id": "subflow::fan_template",
                    "name": "Fan Template",
                    "inputs": 2,
                    "outputs": 1,
                    "in_ports": [
                        {"port_index": 0, "name": "run", "x": 40, "y": 80},
                        {"port_index": 1, "name": "fault", "x": 40, "y": 140},
                    ],
                    "out_ports": [
                        {"port_index": 0, "name": "cmd", "x": 420, "y": 110},
                    ],
                    "raw_definition": {
                        "id": "fan_template",
                        "type": "subflow",
                        "name": "Fan Template",
                        "in": [
                            {"x": 40, "y": 80, "name": "run", "wires": []},
                            {"x": 40, "y": 140, "name": "fault", "wires": []},
                        ],
                        "out": [
                            {"x": 420, "y": 110, "name": "cmd", "wires": []},
                        ],
                    },
                }
            ],
            "node_instances": [
                {
                    "instance_id": "node::fan_ctrl",
                    "logic_id": "fan_ctrl",
                    "module_type": "fan_template",
                    "page_id": "page_control",
                    "subflow_id": None,
                    "template_id": "subflow::fan_template",
                    "parameters": {},
                    "position": {"x": 200, "y": 120},
                    "input_count": 2,
                    "output_count": 1,
                    "reasoning": "reuse subflow",
                }
            ],
            "edges": [],
            "signal_registry": [],
            "layout_hints": {},
            "unresolved_items": [],
        }

        artifact = self.coding_agent.compile_graph(graph_ir, {"relevant_nodes": [], "metadata": {}})
        flow_objects = artifact["flow_objects"]

        self.assertEqual(sum(1 for obj in flow_objects if obj["type"] == "tab"), 1)
        self.assertEqual(sum(1 for obj in flow_objects if obj["type"] == "subflow"), 1)
        subflow_instance = next(obj for obj in flow_objects if obj["type"].startswith("subflow:"))
        self.assertEqual(subflow_instance["inputs"], 2)
        self.assertEqual(subflow_instance["outputs"], 1)

    def test_assembly_to_compiler_preserves_subflow_instances(self):
        retrieval_context = {
            "relevant_nodes": [
                {
                    "module_type": "fan_template",
                    "name": "Fan Template",
                    "template_json": {
                        "id": "subflow::fan_template",
                        "type": "subflow",
                        "name": "Fan Template",
                        "in": [
                            {"x": 40, "y": 80, "name": "run", "wires": []},
                            {"x": 40, "y": 140, "name": "fault", "wires": []},
                        ],
                        "out": [
                            {"x": 420, "y": 110, "name": "cmd", "wires": []},
                        ],
                    },
                    "ports_definition": {
                        "inputs": [
                            {"label": "run", "condition": "always"},
                            {"label": "fault", "condition": "always"},
                        ],
                        "outputs": [{"label": "cmd", "condition": "always"}],
                    },
                }
            ],
            "metadata": {},
        }
        execution_plan = {
            "goal": "subflow plan",
            "nodes": [
                {
                    "logic_id": "fan1",
                    "module_type": "fan_template",
                    "parameters": {"name": "Fan 1"},
                    "reasoning": "use subflow",
                }
            ],
            "connections": [],
        }

        graph_ir = self.assembly_agent.assemble(execution_plan, retrieval_context)
        artifact = self.coding_agent.compile_graph(graph_ir, retrieval_context)

        self.assertEqual(graph_ir["node_instances"][0]["template_id"], "subflow::fan_template")
        self.assertEqual(artifact["compile_report"]["warnings"], [])
        self.assertEqual(sum(1 for obj in artifact["flow_objects"] if obj["type"] == "subflow"), 1)
        self.assertEqual(sum(1 for obj in artifact["flow_objects"] if obj["type"].startswith("subflow:")), 1)

    def test_verifier_accepts_phase1_artifact(self):
        graph_ir = self.assembly_agent.assemble(self.execution_plan, self.retrieval_context)
        artifact = self.coding_agent.compile_graph(graph_ir, self.retrieval_context)
        report = self.verifier_agent.verify(graph_ir, artifact)

        self.assertEqual(report["status"], "passed")
        self.assertEqual(len(report["issues"]), 0)

    def test_verifier_rejects_missing_required_inputs(self):
        execution_plan = {
            "goal": "sum with missing input",
            "nodes": [
                {
                    "logic_id": "const_a",
                    "module_type": "constInput",
                    "parameters": {"fixedValue": 1, "name": "A"},
                    "reasoning": "first constant",
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
                }
            ],
        }

        graph_ir = self.assembly_agent.assemble(execution_plan, self.retrieval_context)
        artifact = self.coding_agent.compile_graph(graph_ir, self.retrieval_context)
        report = self.verifier_agent.verify(graph_ir, artifact)

        self.assertEqual(report["status"], "retryable_error")
        self.assertGreater(report["metrics"]["missing_required_inputs"], 0)
        self.assertTrue(
            any(issue["rule_id"] == "ir.node.required_inputs.must_be_wired" for issue in report["issues"])
        )

    def test_compiler_skips_invalid_edges_with_warning(self):
        execution_plan = {
            "goal": "bad edge",
            "nodes": [
                {
                    "logic_id": "const_a",
                    "module_type": "constInput",
                    "parameters": {"fixedValue": 1, "name": "A"},
                    "reasoning": "first constant",
                }
            ],
            "connections": [
                {
                    "from_node": "ghost",
                    "from_port_index": 0,
                    "to_node": "const_a",
                    "to_port_index": 0,
                }
            ],
        }

        graph_ir = self.assembly_agent.assemble(execution_plan, self.retrieval_context)
        artifact = self.coding_agent.compile_graph(graph_ir, self.retrieval_context)
        report = self.verifier_agent.verify(graph_ir, artifact)

        self.assertTrue(
            any("不存在的源实例" in warning for warning in artifact["compile_report"]["warnings"])
        )
        self.assertEqual(report["status"], "retryable_error")
        self.assertTrue(
            any(issue["rule_id"] == "ir.edge.source.must_exist" for issue in report["issues"])
        )

    def test_verifier_rejects_planning_failure_empty_plan_and_zero_node_artifact(self):
        empty_plan = {
            "goal": "规划失败: llm unavailable",
            "nodes": [],
            "connections": [],
        }

        graph_ir = self.assembly_agent.assemble(empty_plan, self.retrieval_context)
        artifact = self.coding_agent.compile_graph(graph_ir, self.retrieval_context)
        report = self.verifier_agent.verify(graph_ir, artifact)

        self.assertEqual(report["status"], "retryable_error")
        rule_ids = {issue["rule_id"] for issue in report["issues"]}
        self.assertIn("plan.generation.must_succeed", rule_ids)
        self.assertIn("plan.nodes.must_not_be_empty", rule_ids)
        self.assertIn("ir.node_instances.must_not_be_empty", rule_ids)
        self.assertIn("compile.nodes.must_not_be_empty", rule_ids)

    def test_verifier_compile_wire_target_port_uses_target_inputs(self):
        graph_ir = {
            "graph_ir_version": "2.0",
            "goal": "wire port check",
            "pages": [
                {"page_id": "page_control", "label": "Control", "kind": "control", "order": 0},
            ],
            "subflow_definitions": [],
            "node_instances": [
                {
                    "instance_id": "node::src",
                    "logic_id": "src",
                    "module_type": "constInput",
                    "page_id": "page_control",
                    "subflow_id": None,
                    "template_id": None,
                    "parameters": {},
                    "position": {"x": 100, "y": 80},
                    "input_count": 0,
                    "output_count": 1,
                    "reasoning": "",
                },
                {
                    "instance_id": "node::dst",
                    "logic_id": "dst",
                    "module_type": "add",
                    "page_id": "page_control",
                    "subflow_id": None,
                    "template_id": None,
                    "parameters": {},
                    "position": {"x": 280, "y": 80},
                    "input_count": 0,
                    "output_count": 1,
                    "reasoning": "",
                },
            ],
            "edges": [],
            "signal_registry": [],
            "layout_hints": {},
            "unresolved_items": [],
            "source_execution_plan": {
                "goal": "wire port check",
                "nodes": [{"logic_id": "src"}, {"logic_id": "dst"}],
                "connections": [],
            },
        }
        flow_objects = [
            {"id": "tab1", "type": "tab", "label": "Control", "disabled": False, "info": ""},
            {
                "id": "src1",
                "type": "constInput",
                "z": "tab1",
                "name": "SRC",
                "x": 100,
                "y": 80,
                "wires": [[{"id": "dst1", "port": 2}]],
                "inputs": 0,
                "outputs": 1,
            },
            {
                "id": "dst1",
                "type": "add",
                "z": "tab1",
                "name": "DST",
                "x": 280,
                "y": 80,
                "wires": [[], [], []],
                "inputs": 1,
                "outputs": 3,
            },
        ]
        compiled_artifact = {
            "json_text": json.dumps(flow_objects, ensure_ascii=False),
            "flow_objects": flow_objects,
            "compile_report": {
                "page_count": 1,
                "subflow_count": 0,
                "node_count": 2,
                "warnings": [],
            },
        }

        report = self.verifier_agent.verify(graph_ir, compiled_artifact)

        self.assertEqual(report["status"], "retryable_error")
        wire_issue = next(
            issue for issue in report["issues"]
            if issue["rule_id"] == "compile.wire.port.range"
        )
        self.assertIn("inputs=1", wire_issue["message"])

    def test_workflow_run_with_stubbed_front_half(self):
        class StubAnalysis:
            def __call__(self, state):
                state["analysis_result"] = {"scenario_analysis": {}, "retrieval_plan": {}, "metadata": {}}
                state["requirement_spec"] = {}
                state["current_step"] = "analysis_completed"
                return state

        class StubRetrieval:
            def __call__(self, state):
                state["retrieval_context"] = make_retrieval_context()
                state["retrieval_bundle"] = {}
                state["current_step"] = "retrieval_completed"
                return state

        class StubArchitecturePlanning:
            def __call__(self, state):
                state["decomposition_result"] = {"pages": [], "subsystem_descriptors": [], "shared_signal_registry": [], "template_needs": [], "planning_order": []}
                state["architecture_plan"] = {"goal": "sum two constants", "pages": [], "subsystem_slots": [], "global_constraints": [], "naming_strategy": {}, "layout_strategy": {}, "pattern_bindings": [], "warnings": []}
                state["current_step"] = "architecture_planned"
                return state

        class StubSubsystemPlanning:
            def __call__(self, state):
                state["subsystem_plan_map"] = {
                    "compat_subsystem": {
                        "subsystem_id": "compat_subsystem",
                        "page_id": "page_control",
                        "implementation_mode": "atomic_assembly",
                        "template_binding": {},
                        "node_instances": [],
                        "edges": [],
                        "imported_signals": [],
                        "exported_signals": [],
                        "constraints": [],
                        "unresolved_items": [],
                        "reasoning": "compat stub",
                    }
                }
                state["current_step"] = "subsystem_planned"
                return state

        class StubGlobalAssembly:
            def __call__(self, state):
                state["execution_plan"] = make_execution_plan()
                state["assembled_graph_ir"] = AssemblyAgent().assemble(make_execution_plan(), make_retrieval_context())
                state["current_step"] = "global_assembly_completed"
                return state

        with patch.object(workflow, "AnalysisAgent", StubAnalysis), \
             patch.object(workflow, "RetrievalAgent", StubRetrieval), \
             patch.object(workflow, "ArchitecturePlanner", StubArchitecturePlanning), \
             patch.object(workflow, "SubsystemPlanner", StubSubsystemPlanning), \
             patch.object(workflow, "GlobalAssembler", StubGlobalAssembly):
            result = workflow.run_workflow("sum two constants")

        self.assertIn("assembled_graph_ir", result)
        self.assertIn("compiled_artifact", result)
        self.assertIn("verification_report", result)
        self.assertEqual(result["verification_report"]["status"], "passed")
        self.assertEqual(result["final_output"]["verification_report"]["status"], "passed")
        self.assertEqual(result["generated_code"], result["compiled_artifact"]["json_text"])

    def test_workflow_trace_saves_trace_when_node_raises(self):
        class StubAnalysis:
            def __call__(self, state):
                state["analysis_result"] = {"scenario_analysis": {}, "retrieval_plan": {}, "metadata": {}}
                state["requirement_spec"] = {}
                state["current_step"] = "analysis_completed"
                return state

        class StubRetrieval:
            def __call__(self, state):
                raise RuntimeError("retrieval exploded")

        with patch.object(workflow_trace, "AnalysisAgent", StubAnalysis), \
             patch.object(workflow_trace, "RetrievalAgent", StubRetrieval), \
             patch.object(workflow_trace, "_save_workflow_trace", return_value={"trace_dir": "mock"}) as mock_save:
            with self.assertRaises(RuntimeError):
                workflow_trace.run_workflow("boom")

        mock_save.assert_called_once()


if __name__ == "__main__":
    unittest.main()
