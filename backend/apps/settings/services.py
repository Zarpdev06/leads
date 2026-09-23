"""Typed access to configuration, with env defaults and safe coercion."""
from __future__ import annotations

from typing import Any

from django.conf import settings as django_settings
from django.db import DatabaseError

from .defaults import SETTING_DEFAULTS, default_for, settings_schema
from .models import SettingChangeLog, SystemSetting

_CACHE: dict[str, Any] = {}


def get_setting(key: str, default: Any = None) -> Any:
    """Read a setting: DB → env/default table → provided default."""
    if key in _CACHE:
        return _CACHE[key]
    try:
        row = SystemSetting.objects.filter(key=key).first()
    except DatabaseError:  # migrations not applied yet
        row = None
    if row is not None:
        value = row.secret_value if row.is_secret else row.value
        _CACHE[key] = value
        return value
    value = default_for(key)
    return value if value is not None else default


def set_setting(key: str, value: Any, *, user=None, note: str = "") -> SystemSetting:
    meta = next((row for row in SETTING_DEFAULTS if row[0] == key), None)
    category = meta[2] if meta else "general"
    label = meta[3] if meta else key
    description = meta[4] if meta else ""
    is_secret = meta[5] if meta else False
    is_public = meta[6] if meta else False

    row, _ = SystemSetting.objects.get_or_create(
        key=key,
        defaults={
            "category": category, "label": label, "description": description,
            "is_secret": is_secret, "is_public": is_public,
        },
    )
    old = row.secret_value if row.is_secret else row.value
    if is_secret:
        row.secret_value = value or ""
    else:
        row.value = value
    row.updated_by = user
    row.save()

    SettingChangeLog.objects.create(
        setting=row, key=key, old_value=old if not is_secret else "***",
        new_value=value if not is_secret else "***", changed_by=user, note=note,
    )
    _CACHE.pop(key, None)
    return row


def get_many(keys: list[str]) -> dict[str, Any]:
    return {key: get_setting(key) for key in keys}


def clear_cache() -> None:
    _CACHE.clear()


# ---------------------------------------------------------------------------
# Domain helpers
# ---------------------------------------------------------------------------
def effective_daily_limit() -> int:
    """min(marketing limit, SMTP limit, hard cap) — the number that matters."""
    marketing = int(get_setting("sending.daily_marketing_limit",
                                django_settings.DEFAULT_DAILY_MARKETING_LIMIT) or 0)
    smtp = int(get_setting("sending.smtp_daily_limit", django_settings.SMTP_DAILY_LIMIT) or 0)
    hard_cap = int(django_settings.EMAIL_HARD_DAILY_CAP)
    return max(0, min(marketing, smtp, hard_cap))


def smtp_daily_limit() -> int:
    return int(get_setting("sending.smtp_daily_limit", django_settings.SMTP_DAILY_LIMIT) or 0)


def hard_cap() -> int:
    return int(django_settings.EMAIL_HARD_DAILY_CAP)


def validate_daily_marketing_limit(value: int) -> tuple[int, str | None]:
    """Clamp a requested limit and explain what happened."""
    value = int(value)
    smtp = smtp_daily_limit()
    cap = hard_cap()
    if value > smtp:
        return smtp, f"Reduced to the SMTP limit ({smtp}/day)."
    if value > cap:
        return cap, f"Reduced to the safety cap ({cap}/day)."
    if value < 0:
        return 0, "Limit cannot be negative."
    return value, None


def send_window() -> tuple[str, str]:
    return (
        str(get_setting("sending.window_start", django_settings.SEND_WINDOW_START)),
        str(get_setting("sending.window_end", django_settings.SEND_WINDOW_END)),
    )


def sending_weekdays() -> list[int]:
    value = get_setting("sending.weekdays", django_settings.SEND_WEEKDAYS) or [1, 2, 3, 4, 5]
    return [int(v) for v in value]


def sending_timezone() -> str:
    return str(get_setting("sending.timezone", django_settings.TIME_ZONE) or "UTC")


def min_seconds_between_sends() -> int:
    return int(get_setting("sending.min_seconds_between_sends",
                           django_settings.EMAIL_MIN_SECONDS_BETWEEN_SENDS) or 0)


def max_attempts() -> int:
    return int(get_setting("sending.max_attempts", django_settings.EMAIL_MAX_ATTEMPTS) or 3)


def min_days_between_contacts() -> int:
    return int(get_setting("sending.min_days_between_contacts", 30) or 0)


def max_contacts_per_lead() -> int:
    return int(get_setting("sending.max_contacts_per_lead", 4) or 4)


def smtp_status() -> dict:
    """Report SMTP configuration *without* exposing credentials."""
    host = django_settings.EMAIL_HOST
    user = django_settings.EMAIL_HOST_USER
    return {
        "configured": bool(host and user),
        "host": host or "",
        "port": django_settings.EMAIL_PORT,
        "username": (user[:2] + "***@" + user.split("@")[-1]) if user and "@" in user else "",
        "use_tls": bool(django_settings.EMAIL_USE_TLS),
        "use_ssl": bool(django_settings.EMAIL_USE_SSL),
        "backend": django_settings.EMAIL_BACKEND,
        "password_set": bool(django_settings.EMAIL_HOST_PASSWORD),
        "from_email": django_settings.DEFAULT_FROM_EMAIL,
        "reply_to": django_settings.DEFAULT_REPLY_TO,
    }


def public_settings_payload() -> dict:
    """Settings the SPA is allowed to see (never includes secrets)."""
    payload: dict[str, Any] = {}
    for row in settings_schema():
        key = row["key"]
        if row["is_secret"]:
            payload[key] = "***" if get_setting(key) else ""
            continue
        payload[key] = get_setting(key, row["default"])
    payload["smtp"] = smtp_status()
    payload["effective_daily_limit"] = effective_daily_limit()
    payload["hard_cap"] = hard_cap()
    return payload
