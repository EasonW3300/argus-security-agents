from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


PROVIDERS = {
    "mock": (None, None),
    "qwen": ("https://dashscope.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY"),
    "dashscope": ("https://dashscope.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY"),
    "deepseek": ("https://api.deepseek.com", "DEEPSEEK_API_KEY"),
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY"),
    "openai_compatible": (None, None),
    "custom": (None, None),
}


class ProviderConfig:
    def __init__(self, provider, model, api_key="", base_url=None, response_mode="prompt_json", temperature=0, max_tokens=4096, timeout_seconds=90):
        self.provider = provider
        self.model = model
        self.api_key = api_key or ""
        self.base_url = base_url
        self.response_mode = response_mode
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout_seconds = timeout_seconds

    def public_dict(self):
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "response_mode": self.response_mode,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "timeout_seconds": self.timeout_seconds,
        }


class HarnessConfig:
    def __init__(self, agent, judge):
        self.agent = agent
        self.judge = judge

    @property
    def generator(self):
        return self.agent


def _load_env():
    here = Path(__file__).resolve().parent
    for path in (here / ".env", Path.cwd() / ".env"):
        if path.exists():
            load_dotenv(path, override=False)


def _provider(role, values, inherited=None):
    prefix = "AGENT" if role == "agent" else "JUDGE"
    provider = values.get(prefix + "_PROVIDER") or (inherited.provider if inherited else "mock")
    if provider not in PROVIDERS:
        raise ValueError("%s_PROVIDER must be one of %s" % (prefix, ", ".join(sorted(PROVIDERS))))
    model = values.get(prefix + "_MODEL") or (inherited.model if inherited else None)
    if not model:
        model = "scenario-03-mock" if provider == "mock" else None
    if not model:
        raise ValueError(prefix + "_MODEL is required")
    default_url, key_name = PROVIDERS[provider]
    base_url = values.get(prefix + "_BASE_URL") or default_url
    api_key = values.get(prefix + "_API_KEY") or (values.get(key_name) if key_name else "")
    if provider != "mock" and not base_url:
        raise ValueError(prefix + "_BASE_URL is required")
    if provider != "mock" and not api_key:
        raise ValueError(prefix + "_API_KEY is required")
    return ProviderConfig(
        provider,
        model,
        api_key,
        base_url,
        values.get(prefix + "_RESPONSE_MODE", "prompt_json"),
        float(values.get(prefix + "_TEMPERATURE", "0")),
        int(values.get(prefix + "_MAX_TOKENS", "4096")),
        float(values.get(prefix + "_REQUEST_TIMEOUT_SECONDS", values.get("LLM_REQUEST_TIMEOUT_SECONDS", "90"))),
    )


def load_config(values=None):
    if values is None:
        _load_env()
        values = os.environ
    agent = _provider("agent", values)
    judge = _provider("judge", values, inherited=agent)
    return HarnessConfig(agent, judge)
