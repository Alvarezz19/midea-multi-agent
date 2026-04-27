from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.signal_semantics import (
    canonicalize_signal_name,
    classify_template_input,
    classify_template_output,
)


class Phase4SignalSemanticsTests(unittest.TestCase):
    def test_canonicalize_signal_name_maps_known_aliases(self):
        self.assertEqual(canonicalize_signal_name("控制使能"), "supply_fan_available")
        self.assertEqual(canonicalize_signal_name("送风机可用标志"), "supply_fan_available")
        self.assertEqual(canonicalize_signal_name("schedule_enable"), "schedule_enable")

    def test_classify_template_input_prefers_explicit_external_signal(self):
        classification = classify_template_input(
            "温度设定值",
            requirement_spec={
                "signals": {"inputs": ["温度设定值"], "software_points": [], "alarm_points": [], "outputs": []},
                "global_modes": [],
            },
        )

        self.assertEqual(classification["binding_kind"], "external_input")
        self.assertTrue(classification["allowed_external"])

    def test_classify_template_input_recognizes_shared_signal_alias(self):
        classification = classify_template_input(
            "控制使能",
            requirement_spec={"signals": {"inputs": [], "software_points": [], "alarm_points": [], "outputs": []}, "global_modes": []},
        )

        self.assertEqual(classification["binding_kind"], "shared_signal")
        self.assertFalse(classification["allowed_external"])
        self.assertEqual(classification["canonical_signal_key"], "supply_fan_available")

    def test_classify_template_input_separates_commands_and_parameters(self):
        self.assertEqual(
            classify_template_input("送风机启停手动控制命令")["binding_kind"],
            "external_command",
        )
        self.assertEqual(
            classify_template_input("回风温度设定值")["binding_kind"],
            "external_parameter",
        )

    def test_classify_template_output_only_marks_shared_consumed_outputs(self):
        shared_output = classify_template_output(
            "送风机可用标志",
            consumer_signal_keys=["supply_fan_available_flag"],
        )
        local_output = classify_template_output(
            "电加热控制值",
            consumer_signal_keys=[],
        )

        self.assertEqual(shared_output["binding_kind"], "shared_signal")
        self.assertEqual(local_output["binding_kind"], "subsystem_output")


if __name__ == "__main__":
    unittest.main()
