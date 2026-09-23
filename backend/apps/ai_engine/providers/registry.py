"""Provider registry: how the app picks an adapter at runtime."""
from __future__ import annotations

from typing import Dict, Type

from .anthropic import AnthropicProvider
from .base import AIProvider
from .ollama import OllamaProvider
from .openai import OpenAIProvider
from .rules import RuleBasedProvider

PROVIDERS: Dict[str, Type[AIProvider]] = {
    RuleBasedProvider.key: RuleBasedProvider,
    OpenAIProvider.key: OpenAIProvider,
    AnthropicProvider.key: AnthropicProvider,
    OllamaProvider.key: OllamaProvider,
}


def available_providers() -> list[dict]:
    return [
        {
            "key": key,
            "label": provider.label,
            "requires_api_key": provider.requires_api_key,
        }
        for key, provider in PROVIDERS.items()
    ]


def provider_config_for(key: str) -> dict:
    """Build the config dict for a provider from DB settings + environment."""
    from django.conf import settings

    from apps.settings.services import get_setting

    config = {
        "model": get_setting("ai.model", settings.AI_MODEL) or "",
        "temperature": get_setting("ai.temperature", settings.AI_TEMPERATURE),
        "max_tokens": get_setting("ai.max_tokens", settings.AI_MAX_TOKENS),
        "base_url": get_setting("ai.base_url", settings.AI_BASE_URL) or "",
        "api_key": "",
    }

    try:
        from apps.ai_engine.models import AIProviderConfig

        row = AIProviderConfig.objects.filter(provider=key).first()
        if row is not None:
            config.update({
                "model": row.model or config["model"],
                "temperature": row.temperature if row.temperature is not None else config["temperature"],
                "max_tokens": row.max_tokens or config["max_tokens"],
                "base_url": row.base_url or config["base_url"],
                "api_key": row.api_key or "",
            })
    except Exception:  # pragma: no cover - table may not exist during migrations
        pass

    if not config["api_key"]:
        config["api_key"] = get_setting("ai.api_key", settings.AI_API_KEY) or ""
    return config


def get_provider(key: str | None = None) -> AIProvider:
    """Return the configured provider, falling back to the rule-based one."""
    from django.conf import settings

    from apps.settings.services import get_setting

    key = (key or get_setting("ai.provider", settings.AI_PROVIDER) or "rules").lower()
    if not get_setting("ai.enabled", settings.AI_ENABLED):
        key = "rules"
    provider_cls = PROVIDERS.get(key, RuleBasedProvider)
    config = provider_config_for(key)
    if provider_cls.requires_api_key and not config.get("api_key"):
        # Without credentials we keep campaigns running with the offline engine.
        return RuleBasedProvider(config)
    return provider_cls(config)
