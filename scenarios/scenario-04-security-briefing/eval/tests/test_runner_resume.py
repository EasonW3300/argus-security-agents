import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT.parent / "EvalsData.json"
sys.path.insert(0, str(ROOT))

from config import load_config
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


if __name__ == "__main__":
    unittest.main()
