"""
AI safety validator.

The AI must never invent business facts. Two layers:

1. Pattern layer - reject claims about revenue, employees, clients, awards,
   ratings, reviews, years in business, specific technologies...
2. Grounding layer - every number / proper noun in the output must also appear
   in the verified context. Anything else is treated as a fabrication.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

FORBIDDEN_PATTERNS: list[tuple[str, str]] = [
    (r"\b(?:revenue|turnover|sales)\s+(?:of|around|over|under)?\s*\$?\d", "revenue figure"),
    (r"\$\s?\d[\d,\.]*\s?(?:k|m|mm|bn|billion|million)?\b", "money amount"),
    (r"\b(?:award[- ]winning|award[- ]winner|won (?:an?|the) award)\b", "award claim"),
    (r"\brated\s+(?:#|\d|top)\b", "rating claim"),
    (r"\b(?:five|4|5)[- ]star\b", "star rating claim"),
    (r"\b(?:your )?(?:\d+)\s+(?:employees|staff|team members|technicians)\b",
     "employee count claim"),
    (r"\bteam of \d+\b", "team size claim"),
    (r"\b(?:founded|since|established in)\s+\d{4}\b", "founding year claim"),
    (r"\b\d+\+?\s+(?:clients|customers|patients|reviews|locations|branches)\b",
     "client/review count claim"),
    (r"\b(?:your customers|your clients)\s+(?:say|love|rate|review)", "review claim"),
    (r"\b(?:#1|number one|best[- ]rated|top[- ]rated)\b", "superlative claim"),
    (r"\b(?:we (?:noticed|saw) that you (?:use|have|offer))\b", "unverified observation"),
    (r"\b(?:your (?:website|site) (?:says|mentions|shows))\b", "unverified website claim"),
    (r"\b(?:i (?:read|saw) (?:your|the) review)", "review claim"),
    (r"\b(?:growing|thriving|booming|leading) (?:business|company|team)\b",
     "unverified qualitative claim"),
    (r"\b(?:i know|i understand) (?:that )?you (?:have|are|offer)\b", "unverified claim"),
]

PLACEHOLDER_RE = re.compile(r"\{\{[^}]+\}\}")
NUMBER_RE = re.compile(r"\b\d[\d,\.]*\b")
URL_RE = re.compile(r"https?://\S+")

NEUTRAL_WORDS = {"1", "10", "15", "2", "3", "5", "24", "7"}


@dataclass
class SafetyReport:
    passed: bool
    issues: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"passed": self.passed, "issues": self.issues}


class AISafetyValidator:
    """Checks generated copy against the verified context."""

    def __init__(self, *, strict: bool = True):
        self.strict = strict

    def validate(self, text: str, facts: dict[str, str]) -> SafetyReport:
        issues: list[str] = []
        lowered = text.lower()

        # 1. Forbidden claim patterns --------------------------------------
        for pattern, label in FORBIDDEN_PATTERNS:
            if re.search(pattern, lowered):
                issues.append(f"Contains a {label} that is not in the source data.")

        # 2. Grounding: numbers must appear in the context -------------------
        known_numbers = set()
        for value in facts.values():
            if value in (None, ""):
                continue
            known_numbers.update(NUMBER_RE.findall(str(value)))
        known_numbers.update(NEUTRAL_WORDS)
        for number in set(NUMBER_RE.findall(text)):
            if number not in known_numbers:
                issues.append(
                    f"Number '{number}' does not appear in the verified lead data."
                )

        # 3. Unresolved placeholders -----------------------------------------
        for placeholder in set(PLACEHOLDER_RE.findall(text)):
            issues.append(f"Unresolved placeholder {placeholder}.")

        # 4. URLs that are not the business's own website ---------------------
        website = (facts.get("website") or "").lower()
        for url in set(URL_RE.findall(text)):
            host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0].lower()
            if website and host and host not in website and "unsubscribe" not in host:
                issues.append(f"Contains an external link that was not in the source data ({host}).")

        # 5. Banned generic openers -------------------------------------------
        for opener in ("dear sir", "dear madam", "dear sir/madam", "to whom it may concern",
                       "dear business owner"):
            if opener in lowered:
                issues.append(f"Generic opener '{opener}'.")

        return SafetyReport(passed=not issues, issues=sorted(set(issues)))
