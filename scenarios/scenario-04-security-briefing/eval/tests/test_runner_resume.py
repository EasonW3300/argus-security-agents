import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT.parent / "EvalsData.json"
sys.path.insert(0, str(ROOT))

from config import load_config
from report import write_reports
from run_eval import load_checkpoint_results, run_eval


class RunnerResumeTests(unittest.TestCase):
    def _config(self):
        return load_config({"AGENT_PROVIDER": "mock", "JUDGE_PROVIDER": "mock"})

    def test_resume_skips_completed_and_retries_error(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            self.assertEqual(
                run_eval(DATA_PATH, run_dir, self._config(), case_id="S04-001", mock_agent=True),
                0,
            )
            checkpoint = run_dir / "checkpoints" / "S04-001.json"
            before = checkpoint.read_bytes()
            self.assertEqual(
                run_eval(DATA_PATH, run_dir, self._config(), case_id="S04-001", mock_agent=True, resume=True),
                0,
            )
            self.assertEqual(checkpoint.read_bytes(), before)

            errored = json.loads(checkpoint.read_text(encoding="utf-8"))
            errored["status"] = "error"
            checkpoint.write_text(json.dumps(errored), encoding="utf-8")
            self.assertEqual(
                run_eval(DATA_PATH, run_dir, self._config(), case_id="S04-001", mock_agent=True, resume=True),
                0,
            )
            self.assertEqual(load_checkpoint_results(run_dir)["S04-001"]["status"], "completed")

    def test_negative_grader_failure_is_completed_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            self.assertEqual(
                run_eval(DATA_PATH, run_dir, self._config(), case_id="S04-019", mock_agent=True),
                0,
            )
            result = load_checkpoint_results(run_dir)["S04-019"]

        self.assertEqual(result["status"], "completed")
        self.assertFalse(result["overall_pass"])

    def test_malformed_checkpoint_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            checkpoint_dir = run_dir / "checkpoints"
            checkpoint_dir.mkdir()
            (checkpoint_dir / "S04-001.json").write_text("not json", encoding="utf-8")

            self.assertEqual(load_checkpoint_results(run_dir), {})

    def test_resume_recomputes_completed_checkpoint_when_dataset_changes(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as data_directory:
            run_dir = Path(directory)
            data_path = Path(data_directory) / "EvalsData.json"
            cases = json.loads(DATA_PATH.read_text(encoding="utf-8"))
            data_path.write_text(json.dumps(cases), encoding="utf-8")
            self.assertEqual(run_eval(data_path, run_dir, self._config(), case_id="S04-001", mock_agent=True), 0)
            checkpoint = run_dir / "checkpoints" / "S04-001.json"
            first = json.loads(checkpoint.read_text(encoding="utf-8"))

            cases[0]["mock_source_data"]["alert_stats"]["total"] = 157
            data_path.write_text(json.dumps(cases), encoding="utf-8")
            self.assertEqual(run_eval(data_path, run_dir, self._config(), case_id="S04-001", mock_agent=True, resume=True), 0)
            second = json.loads(checkpoint.read_text(encoding="utf-8"))

        self.assertNotEqual(first["run_provenance"]["dataset_sha256"], second["run_provenance"]["dataset_sha256"])
        self.assertEqual(second["final_output"]["content"]["sections"][0]["data_values"]["alert_stats.total"], 157)

    def test_resume_recomputes_completed_checkpoint_when_agent_mode_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            self.assertEqual(run_eval(DATA_PATH, run_dir, self._config(), case_id="S04-001", mock_agent=True), 0)
            checkpoint = run_dir / "checkpoints" / "S04-001.json"
            first = json.loads(checkpoint.read_text(encoding="utf-8"))
            output = first["final_output"]

            class AgentClient:
                def generate_json(self, messages, label):
                    return type("Call", (), {"parsed": output, "raw_text": json.dumps(output), "to_dict": lambda self: {"label": label}})()

            self.assertEqual(run_eval(DATA_PATH, run_dir, self._config(), case_id="S04-001", mock_agent=False, skip_model_graders=True, resume=True, agent_client=AgentClient()), 0)
            second = json.loads(checkpoint.read_text(encoding="utf-8"))

        self.assertNotEqual(first["run_provenance"]["agent_mode"], second["run_provenance"]["agent_mode"])

    def test_csv_report_uses_lf_line_endings(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            write_reports(
                run_dir,
                {"run": "test"},
                [{
                    "test_case_id": "S04-001",
                    "status": "completed",
                    "type": "daily_report",
                    "difficulty": "easy",
                    "overall_pass": True,
                    "code_graders": {},
                }],
            )
            contents = (run_dir / "eval_summary.csv").read_bytes()

        self.assertNotIn(b"\r\n", contents)


if __name__ == "__main__":
    unittest.main()
