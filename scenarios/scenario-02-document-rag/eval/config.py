from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Mapping, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field, SecretStr


PROVIDERS = {
    "mock": (None, None),
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY"),
    "qwen": ("https://dashscope.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY"),
    "dashscope": ("https://dashscope.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY"),
    "deepseek": ("https://api.deepseek.com", "DEEPSEEK_API_KEY"),
    "openai_compatible": (None, None),
    "custom": (None, None),
}


class ProviderConfig(BaseModel):
    provider: str
    model: str
    api_key: SecretStr = SecretStr("")
    base_url: Optional[str] = None
    response_mode: str = "json_object"
    temperature: Optional[float] = 0
    max_tokens: Optional[int] = 2048
    enable_thinking: Optional[bool] = None
    extra_body: Dict[str, object] = Field(default_factory=dict)

    def public_dict(self):
        public = self.model_dump(exclude={"api_key"})
        if public.get("extra_body"):
            public["extra_body"] = {
                key: ("[REDACTED]" if "key" in key.lower() else value)
                for key, value in public["extra_body"].items()
            }
        return public


class PricingConfig(BaseModel):
    generator_input_per_1m: Optional[float] = Field(default=None, ge=0)
    generator_output_per_1m: Optional[float] = Field(default=None, ge=0)
    judge_input_per_1m: Optional[float] = Field(default=None, ge=0)
    judge_output_per_1m: Optional[float] = Field(default=None, ge=0)


class HarnessConfig(BaseModel):
    generator: ProviderConfig
    judge: ProviderConfig
    pricing: PricingConfig = Field(default_factory=PricingConfig)


def _bool(value):
    if value is None:
        return None
    return str(value).lower() in {"1", "true", "yes", "on"}


def _first(values: Mapping[str, str], *names: str):
    for name in names:
        if values.get(name):
            return values[name]
    return None


def _role(role: str, values: Mapping[str, str], inherited: ProviderConfig = None):
    prefix = role.upper()
    aliases = ("AGENT",) if role == "generator" else ()
    provider = _first(values, prefix + "_PROVIDER", *(a + "_PROVIDER" for a in aliases))
    if not provider and inherited:
        provider = inherited.provider
    if provider not in PROVIDERS:
        raise ValueError("%s_PROVIDER must be one of: %s" % (prefix, ", ".join(sorted(PROVIDERS))))

    model = _first(values, prefix + "_MODEL", *(a + "_MODEL" for a in aliases))
    if not model and inherited:
        model = inherited.model
    if not model:
        raise ValueError("%s_MODEL is required" % prefix)

    default_url, default_key_name = PROVIDERS[provider]
    base_url = _first(values, prefix + "_BASE_URL", *(a + "_BASE_URL" for a in aliases))
    if not base_url:
        base_url = inherited.base_url if inherited and inherited.provider == provider else default_url
    api_key = _first(values, prefix + "_API_KEY", *(a + "_API_KEY" for a in aliases))
    if not api_key and default_key_name:
        api_key = values.get(default_key_name)
    if not api_key and inherited and inherited.provider == provider:
        api_key = inherited.api_key.get_secret_value()
    if provider not in {"mock"} and not base_url:
        raise ValueError("%s_BASE_URL is required for provider %s" % (prefix, provider))
    if provider not in {"mock"} and not api_key:
        raise ValueError("%s_API_KEY is required for provider %s" % (prefix, provider))

    response_mode = _first(values, prefix + "_RESPONSE_MODE", *(a + "_RESPONSE_MODE" for a in aliases))
    temperature = _first(values, prefix + "_TEMPERATURE", *(a + "_TEMPERATURE" for a in aliases))
    max_tokens = _first(values, prefix + "_MAX_TOKENS", *(a + "_MAX_TOKENS" for a in aliases))
    extra = _first(values, prefix + "_EXTRA_BODY_JSON", *(a + "_EXTRA_BODY_JSON" for a in aliases))
    return ProviderConfig(
        provider=provider,
        model=model,
        api_key=SecretStr(api_key or ""),
        base_url=base_url,
        response_mode=response_mode or (inherited.response_mode if inherited else "json_object"),
        temperature=float(temperature) if temperature else (inherited.temperature if inherited else 0),
        max_tokens=int(max_tokens) if max_tokens else (inherited.max_tokens if inherited else 2048),
        enable_thinking=_bool(_first(values, prefix + "_ENABLE_THINKING", *(a + "_ENABLE_THINKING" for a in aliases))),
        extra_body=json.loads(extra or "{}"),
    )


def _load_env_files():
    here = Path(__file__).resolve().parent
    for candidate in [here / ".env", Path.cwd() / ".env"]:
        if candidate.exists():
            load_dotenv(candidate, override=False)
    load_dotenv(override=False)


def load_config(values: Optional[Mapping[str, str]] = None) -> HarnessConfig:
    if values is None:
        _load_env_files()
        values = os.environ
    generator = _role("generator", values)
    judge = _role("judge", values, inherited=generator)
    pricing = PricingConfig(
        generator_input_per_1m=values.get("GENERATOR_INPUT_COST_PER_1M") or values.get("AGENT_INPUT_COST_PER_1M"),
        generator_output_per_1m=values.get("GENERATOR_OUTPUT_COST_PER_1M") or values.get("AGENT_OUTPUT_COST_PER_1M"),
        judge_input_per_1m=values.get("JUDGE_INPUT_COST_PER_1M"),
        judge_output_per_1m=values.get("JUDGE_OUTPUT_COST_PER_1M"),
    )
    return HarnessConfig(generator=generator, judge=judge, pricing=pricing)

