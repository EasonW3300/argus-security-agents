from __future__ import annotations

import json
import os
from typing import Dict, Mapping, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field, SecretStr


PROVIDERS = {
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY"),
    "deepseek": ("https://api.deepseek.com", "DEEPSEEK_API_KEY"),
    "qwen": ("https://dashscope.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY"),
    "custom": (None, None),
}
SENSITIVE_KEY_PARTS = (
    "api_key",
    "token",
    "secret",
    "authorization",
    "password",
    "credential",
)


def _redact_public(value, api_key, redact_sensitive_keys=True):
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            lowered = str(key).lower()
            public_key = (
                key.replace(api_key, "[REDACTED]")
                if isinstance(key, str) and api_key
                else key
            )
            if redact_sensitive_keys and any(
                part in lowered for part in SENSITIVE_KEY_PARTS
            ):
                redacted[public_key] = "[REDACTED]"
            else:
                redacted[public_key] = _redact_public(
                    item, api_key, redact_sensitive_keys
                )
        return redacted
    if isinstance(value, list):
        return [
            _redact_public(item, api_key, redact_sensitive_keys)
            for item in value
        ]
    if isinstance(value, tuple):
        return tuple(
            _redact_public(item, api_key, redact_sensitive_keys)
            for item in value
        )
    if isinstance(value, str) and api_key:
        return value.replace(api_key, "[REDACTED]")
    return value


class ProviderConfig(BaseModel):
    provider: str
    model: str
    api_key: SecretStr
    base_url: str
    response_mode: str = "json_object"
    temperature: Optional[float] = 0
    max_tokens: Optional[int] = None
    enable_thinking: Optional[bool] = None
    extra_body: Dict[str, object] = Field(default_factory=dict)

    def public_dict(self):
        api_key = self.api_key.get_secret_value()
        public = self.model_dump(exclude={"api_key", "extra_body"})
        public = _redact_public(public, api_key, redact_sensitive_keys=False)
        public["extra_body"] = _redact_public(self.extra_body, api_key)
        return public


class PricingConfig(BaseModel):
    agent_input_per_1m: Optional[float] = Field(
        default=None, ge=0, allow_inf_nan=False
    )
    agent_output_per_1m: Optional[float] = Field(
        default=None, ge=0, allow_inf_nan=False
    )
    judge_input_per_1m: Optional[float] = Field(
        default=None, ge=0, allow_inf_nan=False
    )
    judge_output_per_1m: Optional[float] = Field(
        default=None, ge=0, allow_inf_nan=False
    )


class HarnessConfig(BaseModel):
    agent: ProviderConfig
    judge: ProviderConfig
    pricing: PricingConfig

    def public_dict(self):
        return {"agent": self.agent.public_dict(), "judge": self.judge.public_dict(), "pricing": self.pricing.model_dump()}


def _bool(value):
    if value is None:
        return None
    return value.lower() in {"1", "true", "yes", "on"}


def _role(role, values, inherited=None):
    prefix = role.upper()
    provider = values.get(prefix + "_PROVIDER") or (inherited.provider if inherited else None)
    model = values.get(prefix + "_MODEL") or (inherited.model if inherited else None)
    if provider not in PROVIDERS:
        raise ValueError("%s_PROVIDER must be openai, deepseek, qwen, or custom" % prefix)
    if not model:
        raise ValueError("%s_MODEL is required" % prefix)
    default_url, default_key_name = PROVIDERS[provider]
    base_url = values.get(prefix + "_BASE_URL") or (inherited.base_url if inherited and inherited.provider == provider else default_url)
    api_key = values.get(prefix + "_API_KEY") or (values.get(default_key_name) if default_key_name else None)
    if inherited and inherited.provider == provider:
        api_key = api_key or inherited.api_key.get_secret_value()
    if not base_url:
        raise ValueError("CUSTOM provider requires a base URL")
    if not api_key:
        raise ValueError("%s API key is required" % prefix)
    extra = json.loads(values.get(prefix + "_EXTRA_BODY_JSON", "{}"))
    return ProviderConfig(
        provider=provider, model=model, api_key=SecretStr(api_key), base_url=base_url,
        response_mode=values.get(prefix + "_RESPONSE_MODE", inherited.response_mode if inherited else "json_object"),
        temperature=float(values[prefix + "_TEMPERATURE"]) if values.get(prefix + "_TEMPERATURE") else (inherited.temperature if inherited else 0),
        max_tokens=int(values[prefix + "_MAX_TOKENS"]) if values.get(prefix + "_MAX_TOKENS") else None,
        enable_thinking=_bool(values.get(prefix + "_ENABLE_THINKING")), extra_body=extra,
    )


def load_config(values: Optional[Mapping[str, str]] = None) -> HarnessConfig:
    if values is None:
        load_dotenv()
        values = os.environ
    agent = _role("agent", values)
    judge = _role("judge", values, inherited=agent)
    pricing = PricingConfig(
        agent_input_per_1m=values.get("AGENT_INPUT_COST_PER_1M"),
        agent_output_per_1m=values.get("AGENT_OUTPUT_COST_PER_1M"),
        judge_input_per_1m=values.get("JUDGE_INPUT_COST_PER_1M"),
        judge_output_per_1m=values.get("JUDGE_OUTPUT_COST_PER_1M"),
    )
    return HarnessConfig(agent=agent, judge=judge, pricing=pricing)
