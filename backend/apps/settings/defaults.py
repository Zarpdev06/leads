"""Default values for every setting, and metadata for the Settings UI."""
from __future__ import annotations

from django.conf import settings as django_settings

#: (key, default, category, label, description, is_secret, is_public)
SETTING_DEFAULTS: list[tuple] = [
    # ---- Sending limits & schedule --------------------------------------
    ("sending.daily_marketing_limit", 90, "sending", "Daily marketing limit",
     "Maximum marketing emails sent per calendar day. Can never exceed the SMTP limit.",
     False, True),
    ("sending.smtp_daily_limit", 100, "sending", "SMTP daily limit",
     "Hard quota imposed by your SMTP provider.", False, True),
    ("sending.hard_cap", 90, "sending", "Absolute safety cap",
     "Environment-level guard (EMAIL_HARD_DAILY_CAP). Cannot be raised from this UI.",
     False, True),
    ("sending.window_start", "09:30", "sending", "Send window start", "Local time.", False, True),
    ("sending.window_end", "17:30", "sending", "Send window end", "Local time.", False, True),
    ("sending.weekdays", [1, 2, 3, 4, 5], "sending", "Sending days",
     "ISO weekdays (1 = Monday).", False, True),
    ("sending.min_seconds_between_sends", 20, "sending", "Minimum seconds between sends",
     "Pacing inside the send window to respect SMTP rate limits.", False, True),
    ("sending.max_attempts", 3, "sending", "Max delivery attempts per email", "", False, True),
    ("sending.timezone", "UTC", "sending", "Sending timezone", "", False, True),
    ("sending.min_days_between_contacts", 30, "sending", "Minimum days between contacts",
     "Contact-frequency rule used by the eligibility engine.", False, True),
    ("sending.max_contacts_per_lead", 4, "sending", "Max emails per lead",
     "Including follow-ups.", False, True),

    # ---- Email & SMTP ----------------------------------------------------
    ("email.from_name", "", "email", "Default from name", "", False, True),
    ("email.from_address", "", "email", "Default from address", "", False, True),
    ("email.reply_to", "", "email", "Reply-to address", "", False, True),
    ("email.signature", "", "email", "Default signature (HTML)", "", False, True),
    ("email.track_opens", True, "email", "Track opens", "", False, True),
    ("email.track_clicks", True, "email", "Track clicks", "", False, True),
    ("email.smtp_configured", False, "email", "SMTP configured",
     "Read-only status derived from environment variables.", False, True),

    # ---- AI --------------------------------------------------------------
    ("ai.enabled", True, "ai", "AI enabled", "", False, True),
    ("ai.provider", "rules", "ai", "AI provider",
     "rules | openai | anthropic | ollama", False, True),
    ("ai.model", "", "ai", "Model", "", False, True),
    ("ai.base_url", "", "ai", "Base URL (optional)", "", False, True),
    ("ai.temperature", 0.4, "ai", "Temperature", "", False, True),
    ("ai.max_tokens", 700, "ai", "Max tokens", "", False, True),
    ("ai.api_key", "", "ai", "API key", "Stored encrypted. Never returned by the API.",
     True, False),
    ("ai.auto_personalize", True, "ai", "Generate personalization on campaign start", "",
     False, True),
    ("ai.safety_strict", True, "ai", "Strict fact-checking",
     "Reject AI output that contains facts not present in the lead data.", False, True),
    ("ai.brand_voice", "professional, concise, helpful", "ai", "Brand voice", "", False, True),

    # ---- Scoring ---------------------------------------------------------
    ("scoring.rules", {}, "scoring", "Scoring signals",
     "Partial override of the default signal weights.", False, True),
    ("scoring.thresholds", {"hot": 75, "warm": 50, "cold": 25}, "scoring",
     "Quality thresholds", "", False, True),
    ("scoring.contacted_recently_days", 30, "scoring", "Contacted-recently window (days)",
     "", False, True),

    # ---- Deduplication ----------------------------------------------------
    ("dedupe.min_confidence", 55, "dedupe", "Minimum confidence to create a review row",
     "", False, True),
    ("dedupe.auto_merge_confidence", 100, "dedupe", "Auto-merge threshold",
     "Only exact-email matches (100) are auto-linked; merging is otherwise manual.",
     False, True),
    ("dedupe.enabled", True, "dedupe", "Duplicate detection enabled", "", False, True),

    # ---- Imports ----------------------------------------------------------
    ("imports.chunk_size", 1000, "imports", "Chunk size", "", False, True),
    ("imports.skip_invalid_emails", False, "imports", "Skip rows with invalid emails", "",
     False, True),
    ("imports.import_rows_without_email", True, "imports",
     "Import rows without an email", "They land in 'Missing email leads'.", False, True),
    ("imports.enrich_on_import", False, "imports",
     "Run website enrichment automatically", "", False, True),
    ("imports.max_file_mb", 500, "imports", "Maximum upload size (MB)", "", False, True),

    # ---- CRM --------------------------------------------------------------
    ("crm.default_owner_id", None, "crm", "Default lead owner", "", False, True),
    ("crm.currency", "USD", "crm", "Currency", "", False, True),

    # ---- Compliance -------------------------------------------------------
    ("compliance.legal_name", "", "compliance", "Legal entity name", "", False, True),
    ("compliance.postal_address", "", "compliance", "Postal address (email footer)", "",
     False, True),
    ("compliance.unsubscribe_text", "Don't want to receive emails from us? Unsubscribe",
     "compliance", "Unsubscribe link text", "", False, True),

    # ---- General -----------------------------------------------------------
    ("general.company_name", "Your Company", "general", "Company name", "", False, True),
    ("general.website", "", "general", "Website", "", False, True),
    ("general.support_email", "", "general", "Support email", "", False, True),
]


def default_for(key: str):
    for row in SETTING_DEFAULTS:
        if row[0] == key:
            return row[1]
    # A few values come straight from the environment.
    env_defaults = {
        "sending.daily_marketing_limit": django_settings.DEFAULT_DAILY_MARKETING_LIMIT,
        "sending.smtp_daily_limit": django_settings.SMTP_DAILY_LIMIT,
        "sending.hard_cap": django_settings.EMAIL_HARD_DAILY_CAP,
        "sending.window_start": django_settings.SEND_WINDOW_START,
        "sending.window_end": django_settings.SEND_WINDOW_END,
        "sending.weekdays": django_settings.SEND_WEEKDAYS,
        "sending.min_seconds_between_sends": django_settings.EMAIL_MIN_SECONDS_BETWEEN_SENDS,
        "sending.max_attempts": django_settings.EMAIL_MAX_ATTEMPTS,
        "sending.timezone": django_settings.TIME_ZONE,
        "ai.provider": django_settings.AI_PROVIDER,
        "ai.model": django_settings.AI_MODEL,
        "ai.base_url": django_settings.AI_BASE_URL,
        "ai.temperature": django_settings.AI_TEMPERATURE,
        "ai.max_tokens": django_settings.AI_MAX_TOKENS,
        "ai.enabled": django_settings.AI_ENABLED,
        "email.track_opens": django_settings.TRACK_OPENS,
        "email.track_clicks": django_settings.TRACK_CLICKS,
        "compliance.legal_name": django_settings.COMPANY_LEGAL_NAME,
        "compliance.postal_address": django_settings.COMPANY_POSTAL_ADDRESS,
        "imports.chunk_size": django_settings.IMPORT_CHUNK_SIZE,
        "imports.max_file_mb": django_settings.IMPORT_MAX_FILE_MB,
        "email.from_address": django_settings.DEFAULT_FROM_EMAIL,
        "email.reply_to": django_settings.DEFAULT_REPLY_TO,
    }
    return env_defaults.get(key)


def settings_schema() -> list[dict]:
    return [
        {
            "key": key,
            "default": default,
            "category": category,
            "label": label,
            "description": description,
            "is_secret": is_secret,
            "is_public": is_public,
        }
        for key, default, category, label, description, is_secret, is_public in SETTING_DEFAULTS
    ]
