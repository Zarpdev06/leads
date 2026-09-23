"""Ollama adapter (self-hosted models, e.g. llama3 / mistral)."""
from __future__ import annotations

import json
import re

import httpx

from .base import AIEmailContext, AIEmailResult, AIProvider, AIProviderError, AIServiceResult
from .system_prompt import SYSTEM_PROMPT, build_user_prompt

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3"


class OllamaProvider(AIProvider):
    key = "ollama"
    label = "Ollama (local)"
    requires_api_key = False

    @property
    def url(self) -> str:
        return f"{self.base_url or DEFAULT_BASE_URL}/api/chat"

    def generate_email(self, context: AIEmailContext) -> AIEmailResult:
        model = self.model or DEFAULT_MODEL
        prompt = build_user_prompt(context)
        data = self._post({
            "model": model,
            "stream": False,
            "format": "json",
            "options": {"temperature": self.temperature, "num_predict": self.max_tokens},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        })
        content = ((data.get("message") or {}).get("content")) or ""
        parsed = _parse_json(content)
        return AIEmailResult(
            subject=str(parsed.get("subject", ""))[:400],
            opening_sentence=parsed.get("opening_sentence", ""),
            personalization=parsed.get("personalization", ""),
            value_proposition=parsed.get("value_proposition", ""),
            cta=parsed.get("cta", ""),
            body_html=parsed.get("body_html", ""),
            body_text=re.sub(r"<[^>]+>", "", parsed.get("body_html", "")),
            recommended_service=parsed.get("recommended_service", context.selected_service),
            provider=self.key,
            model=model,
            prompt=prompt,
            raw={"response": data},
        )

    def test_connection(self) -> tuple[bool, str]:
        try:
            response = httpx.get(f"{self.base_url or DEFAULT_BASE_URL}/api/tags", timeout=10)
            if response.status_code == 200:
                names = [m.get("name", "") for m in response.json().get("models", [])]
                return True, f"Connected. Local models: {', '.join(names[:5]) or 'none'}."
            return False, f"HTTP {response.status_code}"
        except Exception as exc:
            return False, str(exc)

    def _post(self, payload: dict) -> dict:
        try:
            response = httpx.post(self.url, json=payload, timeout=180)
        except Exception as exc:
            raise AIProviderError(f"Ollama request failed: {exc}") from exc
        if response.status_code >= 400:
            raise AIProviderError(f"Ollama HTTP {response.status_code}: {response.text[:200]}")
        return response.json()


def _parse_json(content: str) -> dict:
    content = (content or "").strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.S)
        if match:
            return json.loads(match.group(0))
        raise AIProviderError("Model returned no JSON payload.")
