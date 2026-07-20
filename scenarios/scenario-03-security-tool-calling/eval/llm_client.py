from __future__ import annotations

import json
import signal
import threading
import time

from openai import OpenAI

from schemas import LLMCallResult


class LLMCallError(RuntimeError):
    pass


class _RequestTimeout(TimeoutError):
    pass


def _call_with_hard_timeout(fn, timeout_seconds: float):
    """Enforce a wall-clock timeout around sync SDK calls in the main thread."""
    if timeout_seconds <= 0 or threading.current_thread() is not threading.main_thread():
        return fn()

    previous = signal.getsignal(signal.SIGALRM)

    def handler(_signum, _frame):
        raise _RequestTimeout(f"request exceeded {timeout_seconds:.1f}s timeout")

    signal.signal(signal.SIGALRM, handler)
    signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
    try:
        return fn()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


class OpenAICompatibleLLMClient:
    def __init__(self, config, completions=None):
        self.config = config
        self.timeout_seconds = getattr(config, "timeout_seconds", 90)
        if completions is None:
            completions = OpenAI(api_key=config.api_key, base_url=config.base_url, timeout=self.timeout_seconds, max_retries=0).chat.completions
        self.completions = completions

    def generate_json(self, messages, label):
        started = time.perf_counter()
        kwargs = {"model": self.config.model, "messages": messages, "temperature": self.config.temperature, "max_tokens": self.config.max_tokens}
        if self.config.response_mode == "json_object":
            kwargs["response_format"] = {"type": "json_object"}
        last = None
        for attempt in range(1, 4):
            try:
                response = _call_with_hard_timeout(
                    lambda: self.completions.create(**kwargs), self.timeout_seconds
                )
                text = response.choices[0].message.content or ""
                parsed = json.loads(text)
                usage = getattr(response, "usage", None)
                return LLMCallResult(label, parsed, text, self.config.provider, self.config.model, self.config.response_mode, getattr(usage, "prompt_tokens", None), getattr(usage, "completion_tokens", None), round((time.perf_counter() - started) * 1000), attempt)
            except Exception as exc:
                last = exc
                if attempt < 3:
                    time.sleep(attempt)
        raise LLMCallError("LLM JSON call failed: %s" % last)
