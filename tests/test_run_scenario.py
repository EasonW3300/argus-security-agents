from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "integration" / "run_scenario.py"
SPEC = importlib.util.spec_from_file_location("run_scenario", MODULE_PATH)
assert SPEC and SPEC.loader
RUNNER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RUNNER
SPEC.loader.exec_module(RUNNER)


class RunScenarioTests(unittest.TestCase):
    def parse(self, *args: str):
        return RUNNER.parse_args(args)

    def test_scenario_one_model_command_uses_run_id(self):
        spec, command, _ = RUNNER.build_command(
            self.parse("--scenario", "scenario-01", "--mode", "model", "--case-id", "A01", "--run-id", "smoke")
        )
        self.assertEqual(spec.key, "scenario-01")
        self.assertEqual(command, ["python3", "run_eval.py", "--run-id", "smoke", "--case-id", "A01"])

    def test_scenario_two_mock_uses_mock_provider(self):
        _, command, env = RUNNER.build_command(
            self.parse("--scenario", "scenario-02", "--mode", "mock", "--limit", "3")
        )
        self.assertIn("--mock-agent", command)
        self.assertIn("--skip-model-graders", command)
        self.assertEqual(env["GENERATOR_PROVIDER"], "mock")

    def test_scenario_three_mock_uses_isolated_run_directory(self):
        _, command, env = RUNNER.build_command(
            self.parse("--scenario", "scenario-03", "--mode", "mock", "--run-id", "baseline")
        )
        self.assertEqual(command[:4], ["python3", "run_eval.py", "--run-dir", str(RUNNER.RESULTS_ROOT / "scenario-03" / "baseline")])
        self.assertEqual(env["AGENT_PROVIDER"], "mock")

    def test_scenario_four_tests_command(self):
        spec, command, _ = RUNNER.build_command(self.parse("--scenario", "scenario-04"))
        self.assertEqual(spec.key, "scenario-04")
        self.assertEqual(command, ["python3", "run_tests.py"])

    def test_scenario_one_rejects_mock(self):
        with self.assertRaisesRegex(ValueError, "no deterministic Mock Agent"):
            RUNNER.build_command(self.parse("--scenario", "scenario-01", "--mode", "mock"))

    def test_rejects_unsafe_run_id(self):
        with self.assertRaisesRegex(ValueError, "must use only"):
            RUNNER.build_command(self.parse("--scenario", "scenario-02", "--mode", "model", "--run-id", "../bad"))

    def test_tests_mode_rejects_eval_flags(self):
        with self.assertRaisesRegex(ValueError, "does not accept"):
            RUNNER.build_command(self.parse("--scenario", "scenario-04", "--case-id", "S04-001"))

    def test_harness_result_directories_match_legacy_scenarios(self):
        self.assertEqual(
            RUNNER.harness_result_dir(RUNNER.SCENARIOS["scenario-01"], "sample"),
            RUNNER.SCENARIOS["scenario-01"].eval_dir / "output" / "sample",
        )
        self.assertEqual(
            RUNNER.harness_result_dir(RUNNER.SCENARIOS["scenario-02"], "sample"),
            RUNNER.SCENARIOS["scenario-02"].eval_dir / "results" / "sample",
        )
        self.assertIsNone(RUNNER.harness_result_dir(RUNNER.SCENARIOS["scenario-03"], "sample"))


if __name__ == "__main__":
    unittest.main()
