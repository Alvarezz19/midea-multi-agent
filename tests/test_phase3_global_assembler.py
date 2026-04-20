from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
from agents.assembly_agent import AssemblyAgent
from agents.coding_agent import CodingAgent
from agents.global_assembler import GlobalAssembler
from agents.verifier_agent import VerifierAgent


def make_bundle() -> dict:
    return {
        "atomic_modules": [
            {
                "module_type": "constInput",
                "name": "Constant Input",
                "category": "logic/basic",
                "description": "Provide a constant numeric value.",
                "parameters_schema": {"fixedValue": {"type": "number"}},
                "ports_definition": {"inputs": [], "outputs": [{"index": 0, "label": "out"}]},
                "template_json": {"type": "constInput", "inputs": 0, "outputs": 1},
            }
        ],
        "subflow_templates": [
            {
                "module_type": "fan_template",
                "asset_type": "subflow_template",
                "template_id": "fan_template",
                "definition_id": "fan_template",
                "template_name": "送风机标准控制",
                "template_role": "supply_fan_control",
                "name": "送风机标准控制",
                "category": "AHU/subflow_templates/fan_control",
                "description": "Reusable fan control subflow.",
                "parameters_schema": {},
                "ports_definition": {
                    "inputs": [],
                    "outputs": [{"index": 0, "label": "supply_fan_available_flag"}],
                },
                "template_json": {
                    "type": "subflow",
                    "id": "fan_template",
                    "name": "送风机标准控制",
                    "in": [],
                    "out": [{"x": 380, "y": 110, "name": "supply_fan_available_flag", "wires": []}],
                    "inputs": 0,
                    "outputs": 1,
                },
                "compile_hints": {"input_count": 0, "output_count": 1},
            },
            {
                "module_type": "heater_template",
                "asset_type": "subflow_template",
                "template_id": "heater_template",
                "definition_id": "heater_template",
                "template_name": "电加热标准控制",
                "template_role": "heater_control",
                "name": "电加热标准控制",
                "category": "AHU/subflow_templates/heater_control",
                "description": "Reusable heater control subflow.",
                "parameters_schema": {},
                "ports_definition": {
                    "inputs": [{"index": 0, "label": "supply_fan_available_flag"}],
                    "outputs": [{"index": 0, "label": "heater_enable"}],
                },
                "template_json": {
                    "type": "subflow",
                    "id": "heater_template",
                    "name": "电加热标准控制",
                    "in": [{"x": 60, "y": 80, "name": "supply_fan_available_flag", "wires": []}],
                    "out": [{"x": 380, "y": 110, "name": "heater_enable", "wires": []}],
                    "inputs": 1,
                    "outputs": 1,
                },
                "compile_hints": {"input_count": 1, "output_count": 1},
            },
        ],
        "system_patterns": [],
        "style_guides": [],
        "metadata": {},
    }


def make_requirement_spec() -> dict:
    return {
        "schema_version": "3.0",
        "system_type": "AHU",
        "scenario_summary": "送风机与电加热联动控制",
        "subsystems": [],
        "signals": {"inputs": ["schedule_enable"], "outputs": [], "software_points": ["schedule_enable"], "alarm_points": []},
        "required_pages": ["IO/通讯", "控制"],
        "global_modes": ["schedule_enable"],
        "ambiguities": [],
        "assumptions": [],
        "acceptance_criteria": [],
        "confidence": 0.8,
        "warnings": [],
    }


def make_architecture_plan() -> dict:
    return {
        "goal": "送风机与电加热联动控制",
        "pages": [
            {"page_id": "page_io_comm", "label": "IO/通讯", "kind": "io", "order": 0},
            {"page_id": "page_control", "label": "控制", "kind": "control", "order": 1},
        ],
        "subsystem_slots": [
            {"subsystem_id": "supply_fan_ctrl", "page_id": "page_control", "priority": 1},
            {"subsystem_id": "heater_ctrl", "page_id": "page_control", "priority": 2},
        ],
        "shared_signal_registry": [
            {
                "signal_name": "supply_fan_available_flag",
                "signal_key": "supply_fan_available_flag",
                "canonical_signal_key": "supply_fan_available_flag",
                "owner_subsystem_id": "supply_fan_ctrl",
                "allowed_external": False,
                "required_exporter_count": 1,
                "consumers": ["heater_ctrl"],
                "candidate_exporters": ["supply_fan_ctrl"],
                "resolution_status": "resolved",
                "resolution_evidence": ["consumers=heater_ctrl", "exporters=supply_fan_ctrl", "owner=supply_fan_ctrl"],
                "source_reason": "fan export",
            },
        ],
        "global_constraints": [],
        "naming_strategy": {"signal_prefix": "ahu"},
        "layout_strategy": {"page_order": ["page_io_comm", "page_control"]},
        "pattern_bindings": [],
        "warnings": [],
    }


def make_subsystem_plan_map() -> dict:
    return {
        "supply_fan_ctrl": {
            "subsystem_id": "supply_fan_ctrl",
            "page_id": "page_control",
            "implementation_mode": "reuse_template",
            "template_binding": {"template_id": "fan_template"},
            "node_instances": [
                {
                    "logic_id": "fan_main",
                    "module_type": "fan_template",
                    "page_id": "page_control",
                    "template_id": "fan_template",
                    "parameters": {"name": "Supply Fan"},
                    "input_count": 0,
                    "output_count": 1,
                    "position": {"x": 100, "y": 100},
                    "reasoning": "fan template",
                }
            ],
            "edges": [],
            "imported_signals": [],
            "exported_signals": [
                {
                    "signal_name": "supply_fan_available_flag",
                    "signal_key": "supply_fan_available_flag",
                    "canonical_signal_key": "supply_fan_available_flag",
                    "node_logic_id": "fan_main",
                    "port_index": 0,
                    "page_id": "page_control",
                    "binding_kind": "shared_signal",
                    "allowed_external": False,
                }
            ],
            "constraints": [],
            "unresolved_items": [],
            "reasoning": "fan subsystem",
        },
        "heater_ctrl": {
            "subsystem_id": "heater_ctrl",
            "page_id": "page_control",
            "implementation_mode": "reuse_template",
            "template_binding": {"template_id": "heater_template"},
            "node_instances": [
                {
                    "logic_id": "heater_main",
                    "module_type": "heater_template",
                    "page_id": "page_control",
                    "template_id": "heater_template",
                    "parameters": {"name": "Heater"},
                    "input_count": 1,
                    "output_count": 1,
                    "position": {"x": 420, "y": 100},
                    "reasoning": "heater template",
                }
            ],
            "edges": [],
            "imported_signals": [
                {
                    "signal_name": "supply_fan_available_flag",
                    "signal_key": "supply_fan_available_flag",
                    "canonical_signal_key": "supply_fan_available_flag",
                    "node_logic_id": "heater_main",
                    "port_index": 0,
                    "page_id": "page_control",
                    "binding_kind": "shared_signal",
                    "allowed_external": False,
                }
            ],
            "exported_signals": [
                {
                    "signal_name": "heater_enable",
                    "signal_key": "heater_enable",
                    "canonical_signal_key": "heater_enable",
                    "node_logic_id": "heater_main",
                    "port_index": 0,
                    "page_id": "page_control",
                    "binding_kind": "subsystem_output",
                    "allowed_external": False,
                }
            ],
            "constraints": [],
            "unresolved_items": [],
            "reasoning": "heater subsystem",
        },
    }


class Phase3GlobalAssemblerTests(unittest.TestCase):
    def test_global_assembler_no_longer_inherits_legacy_assembly_agent(self):
        self.assertFalse(issubclass(GlobalAssembler, AssemblyAgent))

    def test_global_assembler_merges_pages_and_shared_signals(self):
        with patch.object(config, "DEBUG", False):
            assembler = GlobalAssembler()
            graph_ir = assembler.assemble(
                architecture_plan=make_architecture_plan(),
                subsystem_plan_map=make_subsystem_plan_map(),
                retrieval_bundle=make_bundle(),
                requirement_spec=make_requirement_spec(),
            )

        self.assertEqual(len(graph_ir["pages"]), 2)
        self.assertEqual(len(graph_ir["subflow_definitions"]), 2)
        self.assertEqual(len(graph_ir["node_instances"]), 2)
        self.assertEqual(len(graph_ir["edges"]), 1)
        self.assertEqual(graph_ir["edges"][0]["from_instance"], "node::supply_fan_ctrl::fan_main")
        self.assertEqual(graph_ir["edges"][0]["to_instance"], "node::heater_ctrl::heater_main")
        self.assertNotIn("source_execution_plan", graph_ir)

        artifact = CodingAgent().compile_graph_from_bundle(graph_ir, make_bundle())
        report = VerifierAgent().verify(graph_ir, artifact)
        self.assertEqual(report["status"], "passed")

    def test_global_assembler_rejects_synthetic_shared_signal_source_for_internal_signal(self):
        subsystem_plan_map = make_subsystem_plan_map()
        subsystem_plan_map["supply_fan_ctrl"]["exported_signals"] = []

        with patch.object(config, "DEBUG", False):
            assembler = GlobalAssembler()
            graph_ir = assembler.assemble(
                architecture_plan=make_architecture_plan(),
                subsystem_plan_map=subsystem_plan_map,
                retrieval_bundle=make_bundle(),
                requirement_spec=make_requirement_spec(),
            )

        self.assertTrue(
            any(item.get("type") == "synthetic_shared_signal_source" for item in graph_ir["unresolved_items"])
        )
        unresolved = next(
            item for item in graph_ir["unresolved_items"]
            if item.get("type") == "synthetic_shared_signal_source"
        )
        self.assertEqual(unresolved["resolution_status"], "missing_exporter")
        self.assertEqual(unresolved["consumer_subsystem_ids"], ["heater_ctrl"])

        artifact = CodingAgent().compile_graph_from_bundle(graph_ir, make_bundle())
        report = VerifierAgent().verify(graph_ir, artifact)
        self.assertEqual(report["status"], "retryable_error")
        self.assertTrue(
            any(issue.get("rule_id") == "ir.unresolved.synthetic_shared_signal_source" for issue in report["issues"])
        )

    def test_global_assembler_allows_external_placeholder_for_declared_global_mode(self):
        subsystem_plan_map = make_subsystem_plan_map()
        subsystem_plan_map["supply_fan_ctrl"]["imported_signals"] = [
            {
                "signal_name": "schedule_enable",
                "signal_key": "schedule_enable",
                "canonical_signal_key": "schedule_enable",
                "node_logic_id": "fan_main",
                "port_index": 0,
                "page_id": "page_control",
                "binding_kind": "external_input",
                "allowed_external": True,
            }
        ]
        subsystem_plan_map["supply_fan_ctrl"]["node_instances"][0]["input_count"] = 1

        with patch.object(config, "DEBUG", False):
            assembler = GlobalAssembler()
            graph_ir = assembler.assemble(
                architecture_plan=make_architecture_plan(),
                subsystem_plan_map=subsystem_plan_map,
                retrieval_bundle=make_bundle(),
                requirement_spec=make_requirement_spec(),
            )

        self.assertFalse(
            any(item.get("type") == "synthetic_shared_signal_source" for item in graph_ir["unresolved_items"])
        )
        self.assertTrue(
            any(edge["to_instance"] == "node::supply_fan_ctrl::fan_main" for edge in graph_ir["edges"])
        )

    def test_global_assembler_records_unresolved_item_for_ambiguous_shared_signal(self):
        subsystem_plan_map = make_subsystem_plan_map()
        architecture_plan = make_architecture_plan()
        architecture_plan["shared_signal_registry"][0]["owner_subsystem_id"] = ""
        architecture_plan["shared_signal_registry"][0]["candidate_exporters"] = ["backup_fan_ctrl", "supply_fan_ctrl"]
        architecture_plan["shared_signal_registry"][0]["resolution_status"] = "ambiguous"
        architecture_plan["shared_signal_registry"][0]["resolution_evidence"] = [
            "consumers=heater_ctrl",
            "exporters=backup_fan_ctrl, supply_fan_ctrl",
            "multiple exporter candidates detected",
        ]
        subsystem_plan_map["backup_fan_ctrl"] = {
            "subsystem_id": "backup_fan_ctrl",
            "page_id": "page_control",
            "implementation_mode": "reuse_template",
            "template_binding": {"template_id": "fan_template"},
            "node_instances": [
                {
                    "logic_id": "backup_fan_main",
                    "module_type": "fan_template",
                    "page_id": "page_control",
                    "template_id": "fan_template",
                    "parameters": {"name": "Backup Fan"},
                    "input_count": 0,
                    "output_count": 1,
                    "position": {"x": 100, "y": 260},
                    "reasoning": "backup fan template",
                }
            ],
            "edges": [],
            "imported_signals": [],
            "exported_signals": [
                {
                    "signal_name": "supply_fan_available_flag",
                    "signal_key": "supply_fan_available_flag",
                    "canonical_signal_key": "supply_fan_available_flag",
                    "node_logic_id": "backup_fan_main",
                    "port_index": 0,
                    "page_id": "page_control",
                    "binding_kind": "shared_signal",
                    "allowed_external": False,
                }
            ],
            "constraints": [],
            "unresolved_items": [],
            "reasoning": "backup fan subsystem",
        }

        with patch.object(config, "DEBUG", False):
            assembler = GlobalAssembler()
            graph_ir = assembler.assemble(
                architecture_plan=architecture_plan,
                subsystem_plan_map=subsystem_plan_map,
                retrieval_bundle=make_bundle(),
                requirement_spec=make_requirement_spec(),
            )

        self.assertTrue(
            any(item.get("type") == "ambiguous_shared_signal" for item in graph_ir["unresolved_items"])
        )
        unresolved = next(
            item for item in graph_ir["unresolved_items"]
            if item.get("type") == "ambiguous_shared_signal"
        )
        self.assertEqual(unresolved["resolution_status"], "ambiguous")
        self.assertEqual(unresolved["candidate_exporters"], ["backup_fan_ctrl", "supply_fan_ctrl"])
        self.assertEqual(unresolved["consumer_subsystem_ids"], ["heater_ctrl"])
        self.assertFalse(
            any(
                edge["to_instance"] == "node::heater_ctrl::heater_main"
                and edge["from_instance"] != "node::placeholder::supply_fan_available_flag"
                for edge in graph_ir["edges"]
            )
        )

        artifact = CodingAgent().compile_graph_from_bundle(graph_ir, make_bundle())
        report = VerifierAgent().verify(graph_ir, artifact)
        self.assertEqual(report["status"], "retryable_error")
        self.assertTrue(
            any(issue.get("rule_id") == "ir.unresolved.ambiguous_shared_signal" for issue in report["issues"])
        )

    def test_global_assembler_projects_structured_edge_locator_for_missing_local_edge_endpoint(self):
        subsystem_plan_map = make_subsystem_plan_map()
        subsystem_plan_map["heater_ctrl"]["edges"] = [
            {
                "edge_id": "edge::heater_ghost",
                "from_node": "ghost_source",
                "from_port": 0,
                "to_node": "heater_main",
                "to_port": 0,
                "signal_name": "schedule_enable",
            }
        ]

        with patch.object(config, "DEBUG", False):
            assembler = GlobalAssembler()
            graph_ir = assembler.assemble(
                architecture_plan=make_architecture_plan(),
                subsystem_plan_map=subsystem_plan_map,
                retrieval_bundle=make_bundle(),
                requirement_spec=make_requirement_spec(),
            )

        unresolved = next(
            item for item in graph_ir["unresolved_items"]
            if item.get("type") == "missing_local_edge_endpoint"
        )
        self.assertEqual(unresolved["edge_ids"], ["edge::heater_ghost"])
        self.assertEqual(
            unresolved["edge_locator"],
            {
                "subsystem_id": "heater_ctrl",
                "edge_id": "edge::heater_ghost",
                "edge_ids": ["edge::heater_ghost"],
                "from_node": "ghost_source",
                "to_node": "heater_main",
            },
        )
        self.assertEqual(unresolved["from_node"], "ghost_source")
        self.assertEqual(unresolved["to_node"], "heater_main")

    def test_global_assembler_prefers_declared_owner_when_multiple_exporters_exist(self):
        subsystem_plan_map = make_subsystem_plan_map()
        subsystem_plan_map["backup_fan_ctrl"] = {
            "subsystem_id": "backup_fan_ctrl",
            "page_id": "page_control",
            "implementation_mode": "reuse_template",
            "template_binding": {"template_id": "fan_template"},
            "node_instances": [
                {
                    "logic_id": "backup_fan_main",
                    "module_type": "fan_template",
                    "page_id": "page_control",
                    "template_id": "fan_template",
                    "parameters": {"name": "Backup Fan"},
                    "input_count": 0,
                    "output_count": 1,
                    "position": {"x": 100, "y": 260},
                    "reasoning": "backup fan template",
                }
            ],
            "edges": [],
            "imported_signals": [],
            "exported_signals": [
                {
                    "signal_name": "supply_fan_available_flag",
                    "signal_key": "supply_fan_available_flag",
                    "canonical_signal_key": "supply_fan_available_flag",
                    "node_logic_id": "backup_fan_main",
                    "port_index": 0,
                    "page_id": "page_control",
                    "binding_kind": "shared_signal",
                    "allowed_external": False,
                }
            ],
            "constraints": [],
            "unresolved_items": [],
            "reasoning": "backup fan subsystem",
        }

        with patch.object(config, "DEBUG", False):
            assembler = GlobalAssembler()
            graph_ir = assembler.assemble(
                architecture_plan=make_architecture_plan(),
                subsystem_plan_map=subsystem_plan_map,
                retrieval_bundle=make_bundle(),
                requirement_spec=make_requirement_spec(),
            )

        self.assertFalse(
            any(item.get("type") == "ambiguous_shared_signal" for item in graph_ir["unresolved_items"])
        )
        shared_edge = next(
            edge for edge in graph_ir["edges"]
            if edge["to_instance"] == "node::heater_ctrl::heater_main"
        )
        self.assertEqual(shared_edge["from_instance"], "node::supply_fan_ctrl::fan_main")


if __name__ == "__main__":
    unittest.main()
