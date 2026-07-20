import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from llm_client import OpenAICompatibleLLMClient
from run_eval import load_checkpoint_results, write_checkpoint
from schemas import CaseResult


class DummyConfig:
    provider = "mock"
    model = "test"
    api_key = ""
    base_url = None
    response_mode = "prompt_json"
    temperature = 0
    max_tokens = 32
    timeout_seconds = 7


class ResumeAndTimeoutTests(unittest.TestCase):
    def test_client_exposes_configured_request_timeout(self):
        client = OpenAICompatibleLLMClient(DummyConfig(), completions=object())
        self.assertEqual(client.timeout_seconds, 7)

    def test_checkpoint_round_trip_and_resume_lookup(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            result = CaseResult("S03-001", "scenario", "single", "easy", True, "completed", final_output={"summary": "ok"})
            write_checkpoint(run_dir, result)
            loaded = load_checkpoint_results(run_dir)
            self.assertIn("S03-001", loaded)
            self.assertEqual(loaded["S03-001"]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
