"""AI personalization, provider abstraction, service matching and safety."""


from apps.ai_engine.generator import build_context, generate_email_for_lead
from apps.ai_engine.models import AIRecommendation
from apps.ai_engine.providers.registry import get_provider
from apps.ai_engine.providers.rules import RuleBasedProvider
from apps.ai_engine.safety import AISafetyValidator
from apps.ai_engine.service_matching import recommend_service
from apps.settings.services import set_setting


def test_default_provider_is_offline_rules(db):
    provider = get_provider()
    assert provider.key == "rules"
    assert provider.requires_api_key is False


def test_rule_provider_generates_business_specific_copy(make_lead, template):
    lead = make_lead(email="owner@acme.com", company_name="ABC Auto Detailing",
                     city="Dallas", state="TX")
    context = build_context(lead, template=template)
    result = RuleBasedProvider({}).generate_email(context)

    assert "ABC Auto Detailing" in result.subject
    assert "auto detailing" in result.body_html.lower()
    assert "Dallas" in result.body_html
    assert "Dear Sir" not in result.body_html
    assert "{{" not in result.body_html
    assert result.recommended_service


def test_generation_is_deterministic(make_lead, template):
    lead = make_lead(email="owner@acme.com", company_name="ABC Auto Detailing")
    first = generate_email_for_lead(lead, template=template, use_cache=False)
    second = generate_email_for_lead(lead, template=template, use_cache=False)
    assert first.subject == second.subject
    assert first.body_html == second.body_html


def test_generation_is_cached(make_lead, template):
    lead = make_lead(email="owner@acme.com")
    generate_email_for_lead(lead, template=template, use_cache=False)
    generate_email_for_lead(lead, template=template)  # cached
    assert AIRecommendation.objects.filter(lead=lead).count() == 1


def test_service_matching_uses_industry_rules(make_lead, services):
    lead = make_lead(email="owner@acme.com")
    recommendation = recommend_service(lead, use_ai=False)
    assert recommendation.method == "rules"
    assert recommendation.service is not None
    assert recommendation.service.name in {s.name for s in services}
    assert recommendation.rationale


def test_service_matching_falls_back_when_no_rules(make_lead):
    lead = make_lead(email="owner@acme.com", with_industry=False)
    recommendation = recommend_service(lead, use_ai=False)
    assert recommendation.service is None or recommendation.method in {"rules", "none"}


def test_safety_validator_rejects_invented_facts():
    validator = AISafetyValidator(strict=True)
    facts = {"business_name": "ABC Auto Detailing", "city": "Dallas",
             "state": "TX", "website": "abcautodetailing.com",
             "sub_industry": "Auto Detailing"}

    report = validator.validate(
        "Congratulations on your award-winning business and 45 employees!", facts)
    assert not report.passed
    assert any("award" in issue for issue in report.issues)
    assert any("45" in issue for issue in report.issues)


def test_safety_validator_accepts_grounded_copy():
    validator = AISafetyValidator(strict=True)
    facts = {"business_name": "ABC Auto Detailing", "city": "Dallas", "state": "TX",
             "website": "abcautodetailing.com", "sub_industry": "Auto Detailing"}
    report = validator.validate(
        "I came across ABC Auto Detailing while looking at auto detailing "
        "businesses in Dallas.", facts)
    assert report.passed, report.issues


def test_safety_validator_flags_generic_opener_and_placeholders():
    validator = AISafetyValidator()
    report = validator.validate("Dear Sir/Madam, hello {{first_name}}", {})
    assert not report.passed
    assert any("placeholder" in issue.lower() for issue in report.issues)
    assert any("opener" in issue.lower() for issue in report.issues)


def test_safety_validator_flags_external_links():
    validator = AISafetyValidator()
    facts = {"website": "acme.com"}
    report = validator.validate("See https://competitor-site.com for details", facts)
    assert not report.passed


def test_ai_generation_falls_back_when_provider_fails(make_lead, template, monkeypatch):
    from apps.ai_engine.providers.base import AIProviderError

    set_setting("ai.provider", "openai")
    set_setting("ai.api_key", "sk-test-key")

    from apps.ai_engine.providers.base import AIProvider

    class BoomProvider(AIProvider):
        key = "openai"
        label = "OpenAI (boom)"
        requires_api_key = True

        def generate_email(self, context):
            raise AIProviderError("provider exploded")

    monkeypatch.setattr("apps.ai_engine.providers.registry.PROVIDERS",
                        {"openai": BoomProvider,
                         "rules": RuleBasedProvider})

    lead = make_lead(email="owner@acme.com", company_name="ABC Auto Detailing")
    result = generate_email_for_lead(lead, template=template, use_cache=False)
    assert "ABC Auto Detailing" in result.subject
    assert "rules-fallback" in result.provider

    set_setting("ai.provider", "rules")
    set_setting("ai.api_key", "")


def test_unsafe_model_output_is_replaced(make_lead, template, monkeypatch):
    """A model that invents facts must never reach a recipient."""
    from apps.ai_engine.providers.openai import OpenAIProvider

    class FabricatingProvider(OpenAIProvider):
        def generate_email(self, context):
            result = super().generate_email(context)
            result.body_html = (
                "<p>Dear Sir, I see your 120 employees generate $4.2M in revenue "
                "and your award-winning team is amazing.</p>"
            )
            result.subject = "About your 120 employees"
            result.personalization = "your 120 employees"
            return result

    set_setting("ai.provider", "openai")
    set_setting("ai.api_key", "sk-test")
    monkeypatch.setattr("apps.ai_engine.providers.registry.PROVIDERS",
                        {"openai": FabricatingProvider, "rules": RuleBasedProvider})

    lead = make_lead(email="owner@acme.com", company_name="ABC Auto Detailing")
    result = generate_email_for_lead(lead, template=template, use_cache=False)
    assert "120" not in result.body_html
    assert "$4.2M" not in result.body_html
    assert "award-winning" not in result.body_html.lower()
    assert "rules-fallback" in result.provider

    recommendation = AIRecommendation.objects.filter(lead=lead).first()
    assert recommendation.safety_notes

    set_setting("ai.provider", "rules")
    set_setting("ai.api_key", "")


def test_ai_api_endpoints(db, api_client, make_lead, template):
    lead = make_lead(email="owner@acme.com", company_name="ABC Auto Detailing")

    overview = api_client.get("/api/ai/")
    assert overview.status_code == 200
    assert overview.data["active_provider"] == "rules"

    generated = api_client.post("/api/ai/generate/",
                                {"lead_id": lead.pk, "template_id": template.pk},
                                format="json")
    assert generated.status_code == 200
    assert generated.data["subject"]

    matched = api_client.post("/api/ai/match-service/",
                              {"lead_id": lead.pk, "use_ai": False}, format="json")
    assert matched.status_code == 200
    assert "service" in matched.data
