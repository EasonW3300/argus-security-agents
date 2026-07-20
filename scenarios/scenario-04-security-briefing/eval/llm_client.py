from __future__ import annotations

import json
import signal
import threading
import time
from dataclasses import asdict, dataclass
from typing import Optional

from openai import OpenAI


@dataclass
class LLMCallResult:
    label: str
    parsed: dict
    raw_text: str
    provider: str
    model: str
    response_mode: str
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    latency_ms: int
    attempts: int

    def to_dict(self) -> dict:
        return asdict(self)


class LLMCallError(RuntimeError):
    def __init__(self, kind: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable


class _HardTimeout(TimeoutError):
    pass


def _call_with_hard_timeout(callable_, timeout_seconds: float):
    """Interrupt a synchronous SDK call at the configured wall-clock deadline."""
    if timeout_seconds <= 0 or threading.current_thread() is not threading.main_thread():
        return callable_()
    previous = signal.getsignal(signal.SIGALRM)

    def on_timeout(_signum, _frame):
        raise _HardTimeout("request exceeded %.1fs hard timeout" % timeout_seconds)

    signal.signal(signal.SIGALRM, on_timeout)
    signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
    try:
        return callable_()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


class OpenAICompatibleLLMClient:
    """Small OpenAI-compatible adapter usable with Qwen and DeepSeek endpoints."""

    def __init__(self, config, completions=None, sleep_fn=time.sleep, clock=time.perf_counter):
        self.config = config
        self.sleep_fn = sleep_fn
        self.clock = clock
        self.timeout_seconds = float(getattr(config, "timeout_seconds", 90))
        if completions is None:
            completions = OpenAI(
                api_key=getattr(config, "api_key", ""),
                base_url=getattr(config, "base_url", None),
                timeout=self.timeout_seconds,
                max_retries=0,
            ).chat.completions
        self.completions = completions

    def _request_kwargs(self, messages):
        kwargs = {"model": self.config.model, "messages": messages}
        if getattr(self.config, "temperature", None) is not None:
            kwargs["temperature"] = self.config.temperature
        if getattr(self.config, "max_tokens", None) is not None:
            kwargs["max_tokens"] = self.config.max_tokens
        response_mode = getattr(self.config, "response_mode", "prompt_json")
        if response_mode == "json_object":
            kwargs["response_format"] = {"type": "json_object"}
        elif response_mode != "prompt_json":
            raise LLMCallError("configuration_error", "unsupported response mode: %s" % response_mode)
        return kwargs

    def _error(self, exc):
        if isinstance(exc, LLMCallError):
            return exc
        if isinstance(exc, (json.JSONDecodeError, _HardTimeout)):
            return LLMCallError("invalid_json" if isinstance(exc, json.JSONDecodeError) else "timeout", str(exc), True)
        status = getattr(exc, "status_code", None)
        return LLMCallError("provider_error", str(exc), status is None or status == 429 or 500 <= status < 600)

    def generate_json(self, messages, label) -> LLMCallResult:
        started = self.clock()
        last_error = None
        for attempt in range(1, 4):
            try:
                response = _call_with_hard_timeout(
                    lambda: self.completions.create(**self._request_kwargs(messages)),
                    self.timeout_seconds,
                )
                text = response.choices[0].message.content or ""
                if not text.strip():
                    raise LLMCallError("empty_response", "empty model response", True)
                parsed = json.loads(text)
                if not isinstance(parsed, dict):
                    raise LLMCallError("invalid_json", "model response must be a JSON object", True)
                usage = getattr(response, "usage", None)
                return LLMCallResult(label, parsed, text, self.config.provider, self.config.model,
                    getattr(self.config, "response_mode", "prompt_json"), getattr(usage, "prompt_tokens", None),
                    getattr(usage, "completion_tokens", None), round((self.clock() - started) * 1000), attempt)
            except Exception as exc:
                last_error = self._error(exc)
                if not last_error.retryable or attempt == 3:
                    raise last_error
                self.sleep_fn(attempt)
        raise last_error
