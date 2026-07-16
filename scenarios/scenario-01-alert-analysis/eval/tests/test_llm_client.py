import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

from pydantic import BaseModel


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import ProviderConfig
from llm_client import LLMCallError, OpenAICompatibleLLMClient


class Payload(BaseModel):
    value: str


class FakeCompletions:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content=outcome))
            ],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=4),
        )


def provider_error(message, status_code=None):
    error = RuntimeError(message)
    if status_code is not None:
        error.status_code = status_code
    return error


class ClientTest(unittest.TestCase):
    def config(self, provider="deepseek", mode="json_object"):
        return ProviderConfig(
            provider=provider,
            model="model",
            api_key="secret",
            base_url="https://example.test/v1",
            response_mode=mode,
        )

    def test_qwen_extra_body_and_json_object(self):
        fake = FakeCompletions(['{"value":"ok"}'])
        cfg = self.config("qwen").model_copy(
            update={
                "enable_thinking": False,
                "extra_body": {"trace_id": "trace"},
            }
        )

        result = OpenAICompatibleLLMClient(
            cfg, completions=fake, sleep_fn=lambda _: None
        ).generate_json([], Payload, "agent")

        self.assertEqual(result.parsed["value"], "ok")
        self.assertEqual(
            fake.calls[0]["response_format"], {"type": "json_object"}
        )
        self.assertEqual(
            fake.calls[0]["extra_body"],
            {"trace_id": "trace", "enable_thinking": False},
        )

    def test_json_schema_mode_sends_strict_schema(self):
        fake = FakeCompletions(['{"value":"ok"}'])

        OpenAICompatibleLLMClient(
            self.config(mode="json_schema"),
            completions=fake,
            sleep_fn=lambda _: None,
        ).generate_json([], Payload, "agent")

        response_format = fake.calls[0]["response_format"]
        self.assertEqual(response_format["type"], "json_schema")
        self.assertEqual(response_format["json_schema"]["name"], "Payload")
        self.assertTrue(response_format["json_schema"]["strict"])
        self.assertEqual(
            response_format["json_schema"]["schema"],
            Payload.model_json_schema(),
        )

    def test_prompt_json_mode_omits_response_format(self):
        fake = FakeCompletions(['{"value":"ok"}'])

        OpenAICompatibleLLMClient(
            self.config(mode="prompt_json"),
            completions=fake,
            sleep_fn=lambda _: None,
        ).generate_json([], Payload, "agent")

        self.assertNotIn("response_format", fake.calls[0])

    def test_optional_request_parameters_are_only_sent_when_configured(self):
        fake = FakeCompletions(['{"value":"ok"}', '{"value":"ok"}'])
        omitted = self.config().model_copy(
            update={"temperature": None, "max_tokens": None}
        )
        configured = self.config().model_copy(
            update={"temperature": 0.25, "max_tokens": 321}
        )
        client = OpenAICompatibleLLMClient(
            omitted, completions=fake, sleep_fn=lambda _: None
        )

        client.generate_json([], Payload, "omitted")
        client.config = configured
        client.generate_json([], Payload, "configured")

        self.assertNotIn("temperature", fake.calls[0])
        self.assertNotIn("max_tokens", fake.calls[0])
        self.assertEqual(fake.calls[1]["temperature"], 0.25)
        self.assertEqual(fake.calls[1]["max_tokens"], 321)

    def test_empty_response_retries(self):
        fake = FakeCompletions(["", '{"value":"ok"}'])
        sleeps = []

        result = OpenAICompatibleLLMClient(
            self.config(), completions=fake, sleep_fn=sleeps.append
        ).generate_json([], Payload, "agent")

        self.assertEqual(result.attempts, 2)
        self.assertEqual(sleeps, [1])

    def test_invalid_json_and_schema_errors_retry(self):
        for invalid in ("not-json", '{"wrong":"shape"}'):
            with self.subTest(invalid=invalid):
                fake = FakeCompletions([invalid, '{"value":"ok"}'])
                result = OpenAICompatibleLLMClient(
                    self.config(),
                    completions=fake,
                    sleep_fn=lambda _: None,
                ).generate_json([], Payload, "agent")

                self.assertEqual(result.attempts, 2)

    def test_rate_limit_server_and_timeout_errors_retry(self):
        errors = (
            provider_error("rate limited", 429),
            provider_error("server failed", 500),
            TimeoutError("timed out"),
        )
        for error in errors:
            with self.subTest(error=error):
                fake = FakeCompletions([error, '{"value":"ok"}'])
                result = OpenAICompatibleLLMClient(
                    self.config(),
                    completions=fake,
                    sleep_fn=lambda _: None,
                ).generate_json([], Payload, "agent")

                self.assertEqual(result.attempts, 2)

    def test_retry_stops_after_three_attempts_with_one_two_backoff(self):
        fake = FakeCompletions(
            [
                provider_error("failed", 503),
                provider_error("failed", 503),
                provider_error("failed", 503),
            ]
        )
        sleeps = []

        with self.assertRaises(LLMCallError) as raised:
            OpenAICompatibleLLMClient(
                self.config(), completions=fake, sleep_fn=sleeps.append
            ).generate_json([], Payload, "agent")

        self.assertTrue(raised.exception.retryable)
        self.assertEqual(len(fake.calls), 3)
        self.assertEqual(sleeps, [1, 2])

    def test_clear_4xx_errors_do_not_retry(self):
        for status in (400, 401, 404):
            with self.subTest(status=status):
                fake = FakeCompletions(
                    [provider_error("bad request secret", status)]
                )
                with self.assertRaises(LLMCallError) as raised:
                    OpenAICompatibleLLMClient(
                        self.config(),
                        completions=fake,
                        sleep_fn=lambda _: None,
                    ).generate_json([], Payload, "agent")

                self.assertFalse(raised.exception.retryable)
                self.assertEqual(len(fake.calls), 1)
                self.assertNotIn("secret", str(raised.exception))
                self.assertIn("[REDACTED]", str(raised.exception))

    def test_success_captures_usage_latency_attempts_and_label(self):
        fake = FakeCompletions(['{"value":"ok"}'])
        ticks = iter((10.0, 10.125))

        result = OpenAICompatibleLLMClient(
            self.config(),
            completions=fake,
            sleep_fn=lambda _: None,
            clock=lambda: next(ticks),
        ).generate_json([], Payload, "judge")

        self.assertEqual(result.label, "judge")
        self.assertEqual(result.input_tokens, 10)
        self.assertEqual(result.output_tokens, 4)
        self.assertEqual(result.latency_ms, 125)
        self.assertEqual(result.attempts, 1)
        self.assertEqual(result.provider, "deepseek")
        self.assertEqual(result.model, "model")
        self.assertEqual(result.response_mode, "json_object")

    def test_unsupported_response_mode_fails_without_provider_call(self):
        fake = FakeCompletions([])

        with self.assertRaises(LLMCallError) as raised:
            OpenAICompatibleLLMClient(
                self.config(mode="xml"),
                completions=fake,
                sleep_fn=lambda _: None,
            ).generate_json([], Payload, "agent")

        self.assertFalse(raised.exception.retryable)
        self.assertEqual(fake.calls, [])


if __name__ == "__main__":
    unittest.main()
