"""Anthropic (Claude) adapter over httpx."""
from __future__ import annotations

import json
import re

import httpx

from .base import AIEmailContext, AIEmailResult, AIProvider, AIProviderError, AIServiceResult
from .system_prompt import SYSTEM_PROMPT, build_user_prompt

DEFAULT_BASE_URL = "https://api.anthropic.com/v1"
DEFAULT_MODEL = "claude-3-5-sonnet-latest"
API_VERSION = "2023-06-01"


class AnthropicProvider(AIProvider):
    key = "anthropic"
    label = "Anthropic"
    requires_api_key = True

    @property
    def url(self) -> str:
        return f"{self.base_url or DEFAULT_BASE_URL}/messages"

    def generate_email(self, context: AIEmailContext) -> AIEmailResult:
        if not self.api_key:
            raise AIProviderError("Anthropic API key is not configured.")
        model = self.model or DEFAULT_MODEL
        prompt = build_user_prompt(context) + "\n\nReturn only JSON, no prose."
        data = self._post({
            "model": model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
        })
        try:
            content = "".join(
                block.get("text", "") for block in data.get("content", [])
                if block.get("type") == "text"
            )
        except Exception as exc:  # pragma: no cover
            raise AIProviderError(f"Unexpected Anthropic response: {data}") from exc
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
            tokens_used=((data.get("usage") or {}).get("input_tokens", 0)
                         + (data.get("usage") or {}).get("output_tokens", 0)) or None,
        )

    def recommend_service(self, context: AIEmailContext,
                          candidates: list[str]) -> AIServiceResult:
        if not candidates:
            return AIServiceResult()
        if not self.api_key:
            return AIServiceResult(candidates[0], 0.5, "No API key; using rule ranking.",
                                   candidates[1:4])
        prompt = (
            f"Business facts: {json.dumps(context.facts(), default=str)}\n"
            f"Candidate services: {json.dumps(candidates)}\n"
            "Return STRICT JSON: {\"service\": str, \"confidence\": float, "
            "\"rationale\": str, \"alternatives\": [str]}"
        )
        data = self._post({
            "model": self.model or DEFAULT_MODEL,
            "max_tokens": 300,
            "temperature": 0.2,
            "messages": [{"role": "user", "content": prompt}],
        })
        content = "".join(
            block.get("text", "") for block in data.get("content", [])
            if block.get("type") == "text"
        )
        parsed = _parse_json(content)
        return AIServiceResult(
            service=parsed.get("service", candidates[0]),
            confidence=float(parsed.get("confidence", 0.6) or 0.6),
            rationale=parsed.get("rationale", ""),
            alternatives=parsed.get("alternatives", candidates[1:4]),
        )

    def test_connection(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "No API key configured."
        try:
            response = httpx.post(
                self.url,
                json={
                    "model": self.model or DEFAULT_MODEL,
                    "max_tokens": 16,
                    "messages": [{"role": "user", "content": "Reply with the word OK."}],
                },
                headers=self._headers(),
                timeout=30,
            )
            if response.status_code == 200:
                return True, "Connected to Anthropic API."
            return False, f"HTTP {response.status_code}: {response.text[:200]}"
        except Exception as exc:
            return False, str(exc)

    def _headers(self) -> dict:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        }

    def _post(self, payload: dict) -> dict:
        try:
            response = httpx.post(self.url, json=payload, headers=self._headers(), timeout=90)
        except Exception as exc:
            raise AIProviderError(f"Anthropic request failed: {exc}") from exc
        if response.status_code >= 400:
            raise AIProviderError(
                f"Anthropic HTTP {response.status_code}: {response.text[:300]}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise AIProviderError("Anthropic returned a non-JSON response.") from exc


def _parse_json(content: str) -> dict:
    content = (content or "").strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.S)
        if match:
            return json.loads(match.group(0))
        raise AIProviderError("Model returned no JSON payload.")
