"""Suppression service: add / remove / check."""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.core.models import log_audit

from .models import Suppression, SuppressionLog


def normalize_for_lookup(email: str) -> str:
    from apps.core.normalizers import normalize_email

    return normalize_email(email).normalized or (email or "").strip().lower()


def is_suppressed(email: str) -> bool:
    key = normalize_for_lookup(email)
    if not key:
        return False
    return (
        Suppression.objects.filter(email_normalized=key, is_active=True)
        .filter(models_active_filter())
        .exists()
    )


def models_active_filter():  # pragma: no cover - tiny helper (kept explicit for clarity)
    from django.db.models import Q

    return Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())


def suppressed_map(emails: list[str]) -> dict[str, Suppression]:
    keys = {normalize_for_lookup(e) for e in emails if e}
    keys.discard("")
    if not keys:
        return {}
    rows = Suppression.objects.filter(
        email_normalized__in=keys, is_active=True
    ).filter(models_active_filter())
    return {row.email_normalized: row for row in rows}


@transaction.atomic
def add_suppression(email: str, *, reason: str = Suppression.Reason.MANUAL_BLOCK,
                    source: str = "MANUAL", note: str = "", actor=None, lead=None,
                    email_message=None, expires_at=None) -> tuple[Suppression, bool]:
    key = normalize_for_lookup(email)
    if not key or "@" not in key:
        raise ValueError("A valid email address is required.")
    row, created = Suppression.objects.get_or_create(
        email_normalized=key,
        defaults={
            "email": (email or "").strip(),
            "reason": reason,
            "source": source,
            "note": note,
            "is_active": True,
            "lead": lead,
            "email_message": email_message,
            "created_by": actor,
            "expires_at": expires_at,
        },
    )
    if not created:
        changed = False
        if not row.is_active:
            row.is_active = True
            changed = True
        if row.reason != reason:
            row.reason = reason
            changed = True
        if note and note not in (row.note or ""):
            row.note = f"{row.note}\n{note}".strip()
            changed = True
        if expires_at and row.expires_at != expires_at:
            row.expires_at = expires_at
            changed = True
        if changed:
            row.save()
    SuppressionLog.objects.create(
        suppression=row,
        email_normalized=key,
        action=SuppressionLog.Action.ADDED if created else SuppressionLog.Action.UPDATED,
        reason=reason,
        note=note,
        actor=actor,
    )
    log_audit(
        action="SUPPRESSION_ADDED",
        actor=actor,
        entity_type="suppression",
        entity_id=row.pk,
        description=f"{key} suppressed ({reason})",
        metadata={"reason": reason, "source": source},
    )
    return row, created


@transaction.atomic
def remove_suppression(email: str, *, actor=None, note: str = "") -> bool:
    """Admin-controlled removal. The action is always logged and auditable."""
    key = normalize_for_lookup(email)
    row = Suppression.objects.filter(email_normalized=key).first()
    if row is None:
        return False
    row.delete()
    SuppressionLog.objects.create(
        email_normalized=key,
        action=SuppressionLog.Action.REMOVED,
        reason=row.reason,
        note=note or "Removed by administrator",
        actor=actor,
    )
    log_audit(
        action="SUPPRESSION_REMOVED",
        actor=actor,
        entity_type="suppression",
        entity_id=key,
        description=f"{key} removed from suppression list",
        metadata={"note": note},
    )
    return True
