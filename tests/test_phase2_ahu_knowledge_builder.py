from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

TEST_TMP_ROOT = PROJECT_ROOT / "outputs" / "test_tmp"
TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)

from utils.ahu_knowledge_builder import build_ahu_knowledge_assets, write_assets_to_chroma


CONTROL = "\u63a7\u5236"
TIMING = "\u5b9a\u65f6"
DX_STATUS = "\u76f4\u81a8\u673a\u72b6\u6001"
EXHAUST_FAN = "\u6392\u98ce\u673a"
IO_COMM = "\u901a\u8baf"
SUBFLOW_NAME = "\u672b\u7aef\u7ec4\u7a7a\u9001\u98ce\u673a\u6807\u51c6\u63a7\u5236"
SUBFLOW_INFO = "\u9001\u98ce\u673a\u542f\u505c\u3001\u6545\u969c\u3001\u53ef\u7528\u6027\u6807\u51c6\u63a7\u5236\u6a21\u677f"
RUN_STATUS = "\u9001\u98ce\u673a\u8fd0\u884c\u72b6\u6001"
FAULT_STATUS = "\u9001\u98ce\u673a\u6545\u969c\u72b6\u6001"
MANUAL_AUTO = "\u9001\u98ce\u673a\u542f\u505c\u624b/\u81ea\u52a8"
RUN_CMD = "\u9001\u98ce\u673a\u8fd0\u884c\u547d\u4ee4"
FAULT_FB = "\u9001\u98ce\u673a\u6545\u969c\u53cd\u9988"
COMPARE = "\u6bd4\u8f83"
LOGIC = "\u903b\u8f91"


def _make_workspace_case_dir() -> Path:
    case_dir = TEST_TMP_ROOT / f"case_{uuid.uuid4().hex}"
    case_dir.mkdir(parents=True, exist_ok=False)
    return case_dir


def _write_flow(path: Path, objects: list[dict]) -> None:
    path.write_text(json.dumps(objects, ensure_ascii=False, indent=2), encoding="utf-8")


def _make_flow_objects(
    flow_id: str,
    extra_page_label: str,
    subflow_id: str,
    internal_objects: list[dict] | None = None,
) -> list[dict]:
    objects = [
        {"id": f"{flow_id}_io", "type": "tab", "label": f"IO/{IO_COMM}({flow_id}\uff09", "disabled": False, "info": ""},
        {"id": f"{flow_id}_control", "type": "tab", "label": CONTROL, "disabled": False, "info": ""},
        {"id": f"{flow_id}_timing", "type": "tab", "label": TIMING, "disabled": False, "info": ""},
        {"id": f"{flow_id}_extra", "type": "tab", "label": extra_page_label, "disabled": False, "info": ""},
        {
            "id": subflow_id,
            "type": "subflow",
            "name": SUBFLOW_NAME,
            "info": SUBFLOW_INFO,
            "in": [
                {"x": 100, "y": 120, "name": RUN_STATUS, "wires": []},
                {"x": 100, "y": 180, "name": FAULT_STATUS, "wires": []},
                {"x": 100, "y": 240, "name": MANUAL_AUTO, "wires": []},
            ],
            "out": [
                {"x": 440, "y": 140, "name": RUN_CMD, "wires": []},
                {"x": 440, "y": 200, "name": FAULT_FB, "wires": []},
            ],
        },
    ]
    if internal_objects is not None:
        objects.extend(internal_objects)
        return objects

    objects.extend(
        [
            {
                "id": f"{subflow_id}_n1",
                "type": "compare",
                "z": subflow_id,
                "name": COMPARE,
                "inputs": 2,
                "outputs": 1,
                "wires": [],
            },
            {
                "id": f"{subflow_id}_n2",
                "type": "logic",
                "z": subflow_id,
                "name": LOGIC,
                "inputs": 2,
                "outputs": 1,
                "wires": [],
            },
        ]
    )
    return objects


class _SimpleEmbeddingFunction:
    TERMS = ("fan", "control", "ahu", "template", "pattern")

    def __call__(self, input):
        texts = [input] if isinstance(input, str) else list(input)
        embeddings = []
        for text in texts:
            lowered = str(text).lower()
            embeddings.append([float(lowered.count(term)) for term in self.TERMS])
        return embeddings

    @staticmethod
    def is_legacy() -> bool:
        return True

    @staticmethod
    def name() -> str:
        return "simple_test_embedding"

    @staticmethod
    def build_from_config(config_data):
        return _SimpleEmbeddingFunction()

    def get_config(self):
        return {}


class AHUKnowledgeBuilderTests(unittest.TestCase):
    def test_subflow_template_id_is_stable_and_excludes_random_id(self):
        tmp_path = _make_workspace_case_dir()
        self.addCleanup(shutil.rmtree, tmp_path, True)
        flows_dir = tmp_path / "flows"
        output_dir = tmp_path / "pattern_library"
        flows_dir.mkdir()

        _write_flow(
            flows_dir / "flows_20240101.json",
            _make_flow_objects("flow_a", DX_STATUS, "subflow_a"),
        )
        _write_flow(
            flows_dir / "flows_20240102.json",
            _make_flow_objects("flow_b", EXHAUST_FAN, "subflow_b"),
        )

        assets_a = build_ahu_knowledge_assets(flows_dir=flows_dir, output_dir=output_dir)
        assets_b = build_ahu_knowledge_assets(flows_dir=flows_dir, output_dir=None)

        self.assertEqual(len(assets_a["subflow_templates"]), 1)
        self.assertEqual(len(assets_b["subflow_templates"]), 1)

        template_a = assets_a["subflow_templates"][0]
        template_b = assets_b["subflow_templates"][0]

        self.assertEqual(template_a["template_id"], template_a["definition_id"])
        self.assertEqual(template_a["module_type"], template_a["template_id"])
        self.assertEqual(template_a["template_json"]["id"], template_a["definition_id"])
        self.assertEqual(template_a["template_id"], template_b["template_id"])
        self.assertIn(template_a["source_info"]["original_subflow_id"], {"subflow_a"})
        self.assertNotIn(template_a["source_info"]["original_subflow_id"], template_a["template_id"])
        self.assertNotIn("subflow_a", template_a["template_id"])
        self.assertNotIn("subflow_b", template_a["template_id"])
        self.assertEqual(
            sorted(template_a["source_info"]["source_flows"]),
            ["flows_20240101.json", "flows_20240102.json"],
        )

        self.assertTrue((output_dir / "subflow_templates.json").exists())
        self.assertTrue((output_dir / "system_patterns.json").exists())
        self.assertTrue((output_dir / "manifest.json").exists())
        self.assertEqual(assets_a["manifest"]["subflow_template_count"], 1)
        self.assertEqual(assets_a["manifest"]["system_pattern_count"], 1)
        self.assertEqual(assets_a["manifest"]["asset_chain_role"], "rebuildable_cache")
        self.assertEqual(len(assets_a["manifest"]["source_flows"]), 2)
        self.assertTrue(all(item["sha1"] for item in assets_a["manifest"]["source_flows"]))

    def test_subflow_template_id_reflects_stable_topology_signature(self):
        tmp_path = _make_workspace_case_dir()
        self.addCleanup(shutil.rmtree, tmp_path, True)
        flows_dir = tmp_path / "flows"
        flows_dir.mkdir()

        topology_a = [
            {
                "id": "node_a_compare",
                "type": "compare",
                "z": "subflow_a",
                "name": "cmp",
                "x": 120,
                "y": 60,
                "inputs": 1,
                "outputs": 1,
                "wires": [[{"id": "node_a_logic", "port": 0}]],
            },
            {
                "id": "node_a_logic",
                "type": "logic",
                "z": "subflow_a",
                "name": "logic",
                "x": 260,
                "y": 60,
                "inputs": 1,
                "outputs": 1,
                "wires": [],
            },
        ]
        topology_same_with_random_ids = [
            {
                "id": "random_1",
                "type": "compare",
                "z": "subflow_b",
                "name": "cmp other",
                "x": 999,
                "y": 300,
                "inputs": 1,
                "outputs": 1,
                "wires": [[{"id": "random_2", "port": 0}]],
            },
            {
                "id": "random_2",
                "type": "logic",
                "z": "subflow_b",
                "name": "logic other",
                "x": 777,
                "y": 200,
                "inputs": 1,
                "outputs": 1,
                "wires": [],
            },
        ]
        topology_different = [
            {
                "id": "node_c_compare",
                "type": "compare",
                "z": "subflow_c",
                "inputs": 1,
                "outputs": 1,
                "wires": [[{"id": "node_c_pid", "port": 0}]],
            },
            {
                "id": "node_c_pid",
                "type": "pid",
                "z": "subflow_c",
                "inputs": 1,
                "outputs": 1,
                "wires": [],
            },
        ]

        _write_flow(
            flows_dir / "flows_20240101.json",
            _make_flow_objects("flow_a", DX_STATUS, "subflow_a", internal_objects=topology_a),
        )
        _write_flow(
            flows_dir / "flows_20240102.json",
            _make_flow_objects("flow_b", EXHAUST_FAN, "subflow_b", internal_objects=topology_same_with_random_ids),
        )
        _write_flow(
            flows_dir / "flows_20240103.json",
            _make_flow_objects("flow_c", EXHAUST_FAN, "subflow_c", internal_objects=topology_different),
        )

        assets = build_ahu_knowledge_assets(flows_dir=flows_dir, output_dir=None)
        templates = assets["subflow_templates"]
        self.assertEqual(len(templates), 2)

        source_sets = {
            frozenset(template["source_info"]["source_flows"]): template["template_id"]
            for template in templates
        }
        self.assertIn(frozenset({"flows_20240101.json", "flows_20240102.json"}), source_sets)
        self.assertIn(frozenset({"flows_20240103.json"}), source_sets)

        merged_id = source_sets[frozenset({"flows_20240101.json", "flows_20240102.json"})]
        different_id = source_sets[frozenset({"flows_20240103.json"})]
        self.assertNotEqual(merged_id, different_id)

    def test_exhaust_fan_page_reuse_creates_alias_template_asset(self):
        tmp_path = _make_workspace_case_dir()
        self.addCleanup(shutil.rmtree, tmp_path, True)
        flows_dir = tmp_path / "flows"
        flows_dir.mkdir()

        objects = _make_flow_objects("flow_alias", EXHAUST_FAN, "subflow_a")
        objects.extend(
            [
                {
                    "id": "flow_alias_exhaust_cmd",
                    "type": "swInput",
                    "z": "flow_alias_extra",
                    "name": "开排风机",
                    "inputs": 0,
                    "outputs": 1,
                    "wires": [[]],
                },
                {
                    "id": "flow_alias_exhaust_instance",
                    "type": "subflow:subflow_a",
                    "z": "flow_alias_extra",
                    "name": "",
                    "inputs": 3,
                    "outputs": 2,
                    "wires": [],
                },
            ]
        )
        _write_flow(flows_dir / "flows_20240101.json", objects)

        assets = build_ahu_knowledge_assets(flows_dir=flows_dir, output_dir=None)
        template_by_role = {template["template_role"]: template for template in assets["subflow_templates"]}

        self.assertIn("supply_fan_control", template_by_role)
        self.assertIn("exhaust_fan_control", template_by_role)
        base_template = template_by_role["supply_fan_control"]
        alias_template = template_by_role["exhaust_fan_control"]

        self.assertNotEqual(alias_template["template_id"], base_template["template_id"])
        self.assertEqual(alias_template["definition_id"], base_template["definition_id"])
        self.assertEqual(alias_template["template_json"]["id"], base_template["definition_id"])
        self.assertEqual(alias_template["source_info"]["alias_of_template_id"], base_template["template_id"])
        self.assertEqual(alias_template["source_info"]["alias_of_template_role"], "supply_fan_control")
        self.assertIn(EXHAUST_FAN, alias_template["template_name"])
        self.assertIn(EXHAUST_FAN, alias_template["description"])
        self.assertIn("开排风机", alias_template["source_info"]["alias_signal_examples"])
        self.assertEqual(assets["manifest"]["subflow_template_count"], 2)

    def test_dependency_module_types_collects_functional_internal_types(self):
        tmp_path = _make_workspace_case_dir()
        self.addCleanup(shutil.rmtree, tmp_path, True)
        flows_dir = tmp_path / "flows"
        flows_dir.mkdir()

        internal_objects = [
            {"id": "n1", "type": "compare", "z": "subflow_a", "inputs": 1, "outputs": 1, "wires": []},
            {"id": "n2", "type": "pid", "z": "subflow_a", "inputs": 1, "outputs": 1, "wires": []},
            {"id": "n3", "type": "switch", "z": "subflow_a", "inputs": 1, "outputs": 1, "wires": []},
            {"id": "n4", "type": "constInput", "z": "subflow_a", "inputs": 0, "outputs": 1, "wires": []},
            {"id": "n5", "type": "subflow:fan_template", "z": "subflow_a", "inputs": 1, "outputs": 1, "wires": []},
            {"id": "n6", "type": "comment", "z": "subflow_a", "name": "note", "wires": []},
            {"id": "n7", "type": "quote", "z": "subflow_a", "name": "quote", "wires": []},
            {"id": "n8", "type": "tab", "z": "subflow_a", "label": "nested", "wires": []},
        ]
        _write_flow(
            flows_dir / "flows_20240101.json",
            _make_flow_objects("flow_a", DX_STATUS, "subflow_a", internal_objects=internal_objects),
        )

        assets = build_ahu_knowledge_assets(flows_dir=flows_dir, output_dir=None)
        dependency_types = set(assets["subflow_templates"][0]["dependency_module_types"])
        self.assertEqual(
            dependency_types,
            {"compare", "pid", "switch", "constInput", "subflow:fan_template"},
        )

    def test_write_assets_to_chroma_cleans_stale_ids(self):
        try:
            import chromadb  # type: ignore
        except Exception:
            self.skipTest("chromadb is not available")

        persist_dir = Path(tempfile.mkdtemp(prefix="phase2-chroma-"))
        self.addCleanup(shutil.rmtree, persist_dir, True)

        collection_names = {
            "subflow_templates": f"phase2_subflow_{uuid.uuid4().hex}",
            "system_patterns": f"phase2_pattern_{uuid.uuid4().hex}",
        }
        assets_v1 = {
            "subflow_templates": [
                {
                    "asset_type": "subflow_template",
                    "template_id": "t1",
                    "template_name": "T1",
                    "description": "template 1",
                    "category": "AHU/test",
                    "template_json": {"type": "subflow", "id": "t1"},
                },
                {
                    "asset_type": "subflow_template",
                    "template_id": "t2",
                    "template_name": "T2",
                    "description": "template 2",
                    "category": "AHU/test",
                    "template_json": {"type": "subflow", "id": "t2"},
                },
            ],
            "system_patterns": [
                {
                    "asset_type": "system_pattern",
                    "pattern_id": "p1",
                    "pattern_name": "P1",
                    "description": "pattern 1",
                    "required_pages": [],
                    "optional_pages": [],
                },
                {
                    "asset_type": "system_pattern",
                    "pattern_id": "p2",
                    "pattern_name": "P2",
                    "description": "pattern 2",
                    "required_pages": [],
                    "optional_pages": [],
                },
            ],
        }
        assets_v2 = {
            "subflow_templates": [assets_v1["subflow_templates"][0]],
            "system_patterns": [assets_v1["system_patterns"][0]],
        }

        embedding = _SimpleEmbeddingFunction()
        with patch("utils.model_manager.EmbeddingManager.get_embedding", return_value=embedding):
            write_assets_to_chroma(
                assets_v1,
                persist_dir=persist_dir,
                collection_names=collection_names,
            )
            write_assets_to_chroma(
                assets_v2,
                persist_dir=persist_dir,
                collection_names=collection_names,
            )

        client = chromadb.PersistentClient(path=str(persist_dir))
        subflow_ids = set(client.get_collection(collection_names["subflow_templates"]).get()["ids"])
        pattern_ids = set(client.get_collection(collection_names["system_patterns"]).get()["ids"])
        self.assertEqual(subflow_ids, {"t1"})
        self.assertEqual(pattern_ids, {"p1"})

    def test_required_and_optional_pages_are_extracted_from_flow_coverage(self):
        tmp_path = _make_workspace_case_dir()
        self.addCleanup(shutil.rmtree, tmp_path, True)
        flows_dir = tmp_path / "flows"
        flows_dir.mkdir()

        _write_flow(
            flows_dir / "flows_20240101.json",
            _make_flow_objects("flow_a", DX_STATUS, "subflow_a"),
        )
        _write_flow(
            flows_dir / "flows_20240102.json",
            _make_flow_objects("flow_b", EXHAUST_FAN, "subflow_b"),
        )

        assets = build_ahu_knowledge_assets(flows_dir=flows_dir, output_dir=None)
        pattern = assets["system_patterns"][0]
        required_keys = {item["page_key"] for item in pattern["required_pages"]}
        optional_keys = {item["page_key"] for item in pattern["optional_pages"]}

        self.assertEqual(pattern["system_type"], "AHU")
        self.assertTrue({"io_comm", "control", "timing"}.issubset(required_keys))
        self.assertIn("dx_status", optional_keys)
        self.assertIn("exhaust_fan", optional_keys)
        self.assertEqual(len(pattern["source_cases"]), 2)


if __name__ == "__main__":
    unittest.main()
