"""Prompt building blocks shared by every provider."""

SYSTEM_PROMPT = """You write short, specific B2B outreach emails for a software
and AI development company.

HARD RULES (breaking them makes the output unusable):
1. Use ONLY the facts provided in the CONTEXT section. Every business fact
   (business name, industry, city, state, website, contact name, job title) must
   come from there.
2. NEVER invent or guess: revenue, employee counts, client names, awards,
   ratings, review counts, certifications, locations, services offered,
   technologies used, years in business, or any other business fact.
3. If a fact is not in the CONTEXT, omit that sentence entirely. Never write
   "your growing team" or "your award-winning business".
4. Never open with "Dear Sir/Madam" or generic filler. The email must make it
   obvious it was written for THIS business and THIS industry.
5. One specific, concrete idea related to the recommended service - not a list
   of everything the company sells.
6. Plain, human language. No hype, no exclamation marks, no emoji.
7. Keep the whole email under 130 words.

Return STRICT JSON with these keys:
  subject            - max 60 characters, no clickbait
  opening_sentence   - one sentence proving you looked at this business
  personalization    - one sentence tied to its industry + location
  value_proposition  - one sentence on the outcome of the recommended service
  cta                - one short question asking for a 10-minute call
  body_html          - the complete email as simple HTML (<p>, <a>, <strong> only)
  recommended_service- echo the recommended service name
"""


def build_user_prompt(context) -> str:
    """Serialize the context for the model (facts only, unknown = 'unknown')."""
    facts = context.facts()
    lines = ["CONTEXT (verified facts only):"]
    for key, value in facts.items():
        lines.append(f"- {key}: {value if value else 'unknown'}")
    available = context.available_information or {}
    if available:
        lines.append("- additional_verified_fields:")
        for key, value in available.items():
            if value:
                lines.append(f"    - {key}: {value}")
    lines.append("")
    lines.append(f"TEMPLATE TO PERSONALIZE:")
    lines.append(f"- subject: {context.template.get('subject', '')}")
    lines.append(f"- body: {context.template.get('body_html', '')}")
    lines.append("")
    lines.append(f"STYLE: {context.brand_voice}")
    if context.extra_instructions:
        lines.append(f"ADDITIONAL INSTRUCTIONS: {context.extra_instructions}")
    lines.append("")
    lines.append(
        "Write the email now. Use {{...}} placeholders ONLY if a variable is "
        "unknown; otherwise write the final text."
    )
    return "\n".join(lines)
