from __future__ import annotations

import json
import time

from openai import OpenAI
from pydantic import ValidationError

from schemas import LLMCallResult


class LLMCallError(RuntimeError):
    def __init__(self, kind, message, retryable=False):
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable


class OpenAICompatibleLLMClient:
    def __init__(
        self,
        config,
        completions=None,
        sleep_fn=time.sleep,
        clock=time.perf_counter,
    ):
        self.config = config
        self.sleep_fn = sleep_fn
        self.clock = clock
        if completions is None:
            completions = OpenAI(
                api_key=config.api_key.get_secret_value(),
                base_url=config.base_url,
            ).chat.completions
        self.completions = completions

    def _request(self, messages, schema):
        kwargs = {"model": self.config.model, "messages": messages}
        if self.config.temperature is not None:
            kwargs["temperature"] = self.config.temperature
        if self.config.max_tokens is not None:
            kwargs["max_tokens"] = self.config.max_tokens

        if self.config.response_mode == "json_object":
            kwargs["response_format"] = {"type": "json_object"}
        elif self.config.response_mode == "json_schema":
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "strict": True,
                    "schema": schema.model_json_schema(),
                },
            }
        elif self.config.response_mode != "prompt_json":
            raise LLMCallError(
                "configuration_error",
                "unsupported response mode: %s" % self.config.response_mode,
                False,
            )

        extra_body = dict(self.config.extra_body)
        if self.config.enable_thinking is not None:
            extra_body["enable_thinking"] = self.config.enable_thinking
        if extra_body:
            kwargs["extra_body"] = extra_body
        return kwargs

    def _redact(self, message):
        api_key = self.config.api_key.get_secret_value()
        return str(message).replace(api_key, "[REDACTED]")

    def _provider_error(self, exc):
        status = getattr(exc, "status_code", None)
        retryable = (
            status == 429
            or (status is not None and 500 <= status < 600)
            or status is None
        )
        return LLMCallError(
            "provider_error", self._redact(exc), retryable=retryable
        )

    def generate_json(self, messages, schema, label):
        started = self.clock()
        last_error = None
        for attempt in range(1, 4):
            try:
                response = self.completions.create(
                    **self._request(messages, schema)
                )
                text = response.choices[0].message.content or ""
                if not text.strip():
                    raise LLMCallError(
                        "empty_response", "empty model response", True
                    )
                parsed = schema.model_validate(json.loads(text))
                usage = getattr(response, "usage", None)
                return LLMCallResult(
                    label=label,
                    parsed=parsed.model_dump(),
                    raw_text=text,
                    provider=self.config.provider,
                    model=self.config.model,
                    response_mode=self.config.response_mode,
                    input_tokens=getattr(usage, "prompt_tokens", None),
                    output_tokens=getattr(
                        usage, "completion_tokens", None
                    ),
                    latency_ms=round((self.clock() - started) * 1000),
                    attempts=attempt,
                )
            except json.JSONDecodeError as exc:
                last_error = LLMCallError(
                    "invalid_json", self._redact(exc), True
                )
            except ValidationError as exc:
                last_error = LLMCallError(
                    "invalid_schema", self._redact(exc), True
                )
            except LLMCallError as exc:
                last_error = exc
            except Exception as exc:
                last_error = self._provider_error(exc)

            if not last_error.retryable or attempt == 3:
                raise last_error
            self.sleep_fn(1 if attempt == 1 else 2)

        raise last_error
