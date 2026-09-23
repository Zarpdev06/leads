"""OpenAI adapter (chat completions API over httpx, no vendor SDK)."""
from __future__ import annotations

import json
import re

import httpx

from .base import AIEmailContext, AIEmailResult, AIProvider, AIProviderError, AIServiceResult
from .system_prompt import SYSTEM_PROMPT, build_user_prompt

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"


class OpenAIProvider(AIProvider):
    key = "openai"
    label = "OpenAI"
    requires_api_key = True

    @property
    def url(self) -> str:
        return f"{self.base_url or DEFAULT_BASE_URL}/chat/completions"

    def generate_email(self, context: AIEmailContext) -> AIEmailResult:
        if not self.api_key:
            raise AIProviderError("OpenAI API key is not configured.")
        model = self.model or DEFAULT_MODEL
        prompt = build_user_prompt(context)
        payload = {
            "model": model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        }
        data = self._post(payload)
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise AIProviderError(f"Unexpected OpenAI response: {data}") from exc

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
            tokens_used=(data.get("usage") or {}).get("total_tokens"),
        )

    def recommend_service(self, context: AIEmailContext,
                          candidates: list[str]) -> AIServiceResult:
        if not candidates:
            return AIServiceResult()
        if not self.api_key:
            return AIServiceResult(candidates[0], 0.5, "No API key; using rule ranking.",
                                   candidates[1:4])
        prompt = (
            "You recommend ONE service from a catalogue for a B2B outreach email.\n"
            f"Business facts: {json.dumps(context.facts(), default=str)}\n"
            f"Candidate services: {json.dumps(candidates)}\n"
            "Return STRICT JSON: {\"service\": str, \"confidence\": float, "
            "\"rationale\": str, \"alternatives\": [str]}"
        )
        data = self._post({
            "model": self.model or DEFAULT_MODEL,
            "temperature": 0.2,
            "max_tokens": 300,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": "You are a precise B2B service recommender."},
                {"role": "user", "content": prompt},
            ],
        })
        parsed = _parse_json(data["choices"][0]["message"]["content"])
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
            response = httpx.get(
                f"{self.base_url or DEFAULT_BASE_URL}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=20,
            )
            if response.status_code == 200:
                models = [m.get("id", "") for m in response.json().get("data", [])]
                return True, f"Connected. {len(models)} models available."
            return False, f"HTTP {response.status_code}: {response.text[:200]}"
        except Exception as exc:
            return False, str(exc)

    def _post(self, payload: dict) -> dict:
        try:
            response = httpx.post(
                self.url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=60,
            )
        except Exception as exc:
            raise AIProviderError(f"OpenAI request failed: {exc}") from exc
        if response.status_code >= 400:
            raise AIProviderError(
                f"OpenAI HTTP {response.status_code}: {response.text[:300]}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise AIProviderError("OpenAI returned a non-JSON response.") from exc


def _parse_json(content: str) -> dict:
    """Tolerant JSON parsing (models sometimes wrap JSON in prose)."""
    content = (content or "").strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError as exc:
                raise AIProviderError(f"Model returned invalid JSON: {exc}") from exc
        raise AIProviderError("Model returned no JSON payload.")
