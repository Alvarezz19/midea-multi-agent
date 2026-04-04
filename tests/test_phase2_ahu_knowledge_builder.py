from __future__ import annotations

import json
import shutil
import sys
import unittest
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

TEST_TMP_ROOT = PROJECT_ROOT / "outputs" / "test_tmp"
TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)

from utils.ahu_knowledge_builder import build_ahu_knowledge_assets


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


def _make_flow_objects(flow_id: str, extra_page_label: str, subflow_id: str) -> list[dict]:
    return [
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
