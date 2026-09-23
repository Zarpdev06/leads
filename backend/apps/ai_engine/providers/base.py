"""
AIProvider interface.

Nothing outside this package talks to a vendor SDK: providers are plain
adapters that receive a context object and return a structured result. Adding a
provider = subclass + registry entry.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class AIEmailContext:
    """Everything the AI is allowed to know about the recipient.

    Fields that are unknown are left empty on purpose: the prompt tells the
    model to omit them rather than invent them.
    """

    business_name: str = ""
    industry: str = ""
    sub_industry: str = ""
    city: str = ""
    state: str = ""
    country: str = ""
    website: str = ""
    contact_name: str = ""
    first_name: str = ""
    job_title: str = ""
    employee_count: str = ""
    available_information: dict[str, Any] = field(default_factory=dict)
    selected_service: str = ""
    template: dict[str, str] = field(default_factory=dict)
    extra_instructions: str = ""
    brand_voice: str = "professional, concise and helpful"
    sender_company: str = ""
    sender_name: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def facts(self) -> dict[str, str]:
        """Only the verified facts - used by the safety validator."""
        return {
            "business_name": self.business_name,
            "industry": self.industry,
            "sub_industry": self.sub_industry,
            "city": self.city,
            "state": self.state,
            "website": self.website,
            "contact_name": self.contact_name,
            "job_title": self.job_title,
            "employee_count": self.employee_count,
            "selected_service": self.selected_service,
        }


@dataclass
class AIServiceResult:
    service: str = ""
    confidence: float = 0.0
    rationale: str = ""
    alternatives: list[str] = field(default_factory=list)


@dataclass
class AIEmailResult:
    subject: str = ""
    opening_sentence: str = ""
    personalization: str = ""
    value_proposition: str = ""
    cta: str = ""
    body_html: str = ""
    body_text: str = ""
    recommended_service: str = ""
    provider: str = ""
    model: str = ""
    prompt: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    tokens_used: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class AIProviderError(Exception):
    """Raised when a provider call fails."""


class AIProvider(ABC):
    """Common contract for every provider adapter."""

    key: str = "base"
    label: str = "Base provider"
    requires_api_key: bool = False

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    # -- capabilities ------------------------------------------------------
    @abstractmethod
    def generate_email(self, context: AIEmailContext) -> AIEmailResult:
        """Generate subject / opening / personalization / value prop / CTA."""

    def recommend_service(self, context: AIEmailContext,
                          candidates: list[str]) -> AIServiceResult:
        """Optional: rank services. Falls back to the rules engine."""
        return AIServiceResult(
            service=candidates[0] if candidates else "",
            confidence=0.0,
            rationale="Provider does not implement service ranking.",
            alternatives=candidates[1:4],
        )

    def test_connection(self) -> tuple[bool, str]:
        """Return (ok, message)."""
        return True, "No external dependency."

    # -- helpers -------------------------------------------------------------
    @property
    def model(self) -> str:
        return self.config.get("model", "") or ""

    @property
    def temperature(self) -> float:
        return float(self.config.get("temperature", 0.4) or 0.4)

    @property
    def max_tokens(self) -> int:
        return int(self.config.get("max_tokens", 700) or 700)

    @property
    def api_key(self) -> str:
        return self.config.get("api_key", "") or ""

    @property
    def base_url(self) -> str:
        return self.config.get("base_url", "") or ""
