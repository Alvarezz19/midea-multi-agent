from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.knowledge_contract_loader import (
    find_subflow_template_contract,
    load_module_contract,
    load_subflow_template_contract,
)


class ModuleContractLoaderTests(unittest.TestCase):
    def test_load_swinput_contract_from_schemas(self):
        contract = load_module_contract("swInput")

        self.assertEqual(contract["module_type"], "swInput")
        self.assertEqual(contract["asset_type"], "atomic_module")
        self.assertIn("parameters_schema", contract)
        self.assertIn("ports_definition", contract)
        self.assertIn("template_json", contract)
        self.assertEqual(contract["template_json"]["type"], "swInput")
        self.assertIn("inputCount", contract["parameters_schema"])
        self.assertIn("source_hash", contract)

    def test_find_supply_fan_template_and_load_internal_body(self):
        template = find_subflow_template_contract(
            template_role="supply_fan_control",
            name_contains="末端组空送风机标准控制",
        )

        self.assertTrue(template["template_id"].startswith("ahu_subflow__"))
        self.assertEqual(template["template_role"], "supply_fan_control")
        self.assertGreaterEqual(len(template["internal_flow_objects"]), 35)

        loaded = load_subflow_template_contract(template["template_id"])
        self.assertEqual(loaded["template_id"], template["template_id"])
        self.assertEqual(len(loaded["internal_flow_objects"]), len(template["internal_flow_objects"]))


if __name__ == "__main__":
    unittest.main()
