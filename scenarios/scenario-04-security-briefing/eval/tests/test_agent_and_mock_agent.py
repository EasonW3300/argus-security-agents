import json
import sys
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from queue import Queue


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT.parent / "EvalsData.json"
sys.path.insert(0, str(ROOT))

from agent_loop import run_agent_case
from llm_client import OpenAICompatibleLLMClient, _HardTimeout, _call_with_hard_timeout
from mock_agent import run_mock_case
from prompt_builder import build_agent_messages
from schemas import load_cases


class AgentAndMockAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = load_cases(DATA_PATH)

    def test_prompt_contains_source_template_and_push_contract(self):
        messages = build_agent_messages(self.cases[0])
        prompt = "\n".join(item["content"] for item in messages)

        self.assertIn("mock_source_data", prompt)
        self.assertIn("template_definition", prompt)
        self.assertIn("target_recipients", prompt)
        self.assertIn("JSON", prompt)

    def test_mock_agent_emits_all_expected_sections(self):
        case = self.cases[0]
        result = run_mock_case(case)
        ids = [section["section_id"] for section in result["final_output"]["content"]["sections"]]

        self.assertEqual(ids, case["ground_truth"]["expected_sections"])
        self.assertEqual(result["final_output"]["target_recipients"], case["push_config"]["recipients"])

    def test_mock_agent_leaks_sensitive_value_for_s04_019(self):
        case = self.cases[18]
        result = run_mock_case(case)
        rendered = json.dumps(result["final_output"], ensure_ascii=False)

        self.assertIn("203.0.113.88", rendered)

    def test_mock_agent_uses_wrong_recipient_for_s04_020(self):
        case = self.cases[19]
        result = run_mock_case(case)

        self.assertEqual(result["final_output"]["target_recipients"], ["all-staff@company.com"])

    def test_agent_loop_serializes_the_model_call(self):
        case = self.cases[0]
        expected = run_mock_case(case)["final_output"]
        call = SimpleNamespace(parsed=expected, raw_text=json.dumps(expected), to_dict=lambda: {"label": "agent"})
        result = run_agent_case(case, SimpleNamespace(generate_json=lambda messages, label: call))

        self.assertEqual(result["final_output"], expected)
        self.assertEqual(result["calls"], [{"label": "agent"}])

    def test_llm_client_retries_invalid_json_then_returns_structured_result(self):
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))],
            usage=SimpleNamespace(prompt_tokens=3, completion_tokens=2),
        )

        class Completions:
            def __init__(self):
                self.calls = 0
                self.kwargs = None

            def create(self, **kwargs):
                self.calls += 1
                self.kwargs = kwargs
                if self.calls == 1:
                    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="not-json"))])
                return response

        config = SimpleNamespace(provider="qwen", model="qwen-test", response_mode="json_object", temperature=0, max_tokens=100, timeout_seconds=1)
        completions = Completions()
        client = OpenAICompatibleLLMClient(config, completions=completions, sleep_fn=lambda _: None)
        result = client.generate_json([{"role": "user", "content": "hi"}], "agent")

        self.assertEqual(result.parsed, {"ok": True})
        self.assertEqual(result.attempts, 2)
        self.assertEqual(completions.kwargs["response_format"], {"type": "json_object"})

    def test_hard_timeout_interrupts_slow_call_on_main_thread(self):
        with self.assertRaises(_HardTimeout):
            _call_with_hard_timeout(lambda: time.sleep(0.2), 0.02)

    def test_hard_timeout_interrupts_slow_call_on_worker_thread(self):
        results = Queue()

        def target():
            started = time.monotonic()
            try:
                _call_with_hard_timeout(lambda: time.sleep(0.2), 0.02)
            except Exception as exc:
                results.put((exc, time.monotonic() - started))

        worker = threading.Thread(target=target, daemon=True)
        worker.start()
        worker.join(0.1)

        self.assertFalse(worker.is_alive(), "worker must not be blocked by the slow call")
        exc, elapsed = results.get_nowait()
        self.assertIsInstance(exc, _HardTimeout)
        self.assertLess(elapsed, 0.1)

    def test_hard_timeout_returns_successful_worker_thread_result(self):
        results = Queue()

        def target():
            results.put(_call_with_hard_timeout(lambda: {"ok": True}, 0.1))

        worker = threading.Thread(target=target)
        worker.start()
        worker.join(0.2)

        self.assertFalse(worker.is_alive())
        self.assertEqual(results.get_nowait(), {"ok": True})


if __name__ == "__main__":
    unittest.main()
