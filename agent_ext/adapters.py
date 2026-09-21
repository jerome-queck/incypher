"""Trusted adapter helpers used by the custom Brain implementation."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


class ConfigurationError(ValueError):
    """Required runtime configuration is absent or malformed."""


def chat_completions_url(base_url: str) -> str:
    """Return one OpenAI-compatible chat-completions URL without duplicating its path."""
    value = (base_url or "").strip().rstrip("/")
    if not value:
        raise ConfigurationError("LLM_BASE_URL is missing")
    if value.endswith("/chat/completions"):
        return value
    return value + "/chat/completions"


@dataclass(frozen=True)
class LLMConfig:
    chat_url: str
    model: str
    api_key: str

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> "LLMConfig":
        missing = [name for name in ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY")
                   if not (environment.get(name) or "").strip()]
        if missing:
            raise ConfigurationError("missing LLM configuration: " + ", ".join(missing))
        return cls(
            chat_url=chat_completions_url(environment["LLM_BASE_URL"]),
            model=environment["LLM_MODEL"].strip(),
            api_key=environment["LLM_API_KEY"].strip(),
        )
