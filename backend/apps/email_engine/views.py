from __future__ import annotations

import base64
import logging

from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import F
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.core.models import log_audit
from apps.core.permissions import CanModify, IsManagerOrAdmin
from apps.leads.models import EmailStatus, Lead, LeadStatus

from .models import DailyEmailUsage, EmailEvent, EmailMessage, EmailTemplate
from .models import FollowUpSequence, FollowUpStep
from .quota import DailyEmailQuota
from .serializers import (
    DailyEmailUsageSerializer,
    EmailEventSerializer,
    EmailMessageDetailSerializer,
    EmailMessageListSerializer,
    EmailTemplateSerializer,
    FollowUpSequenceSerializer,
    FollowUpStepSerializer,
    SendNowSerializer,
    TestEmailSerializer,
)

logger = logging.getLogger(__name__)

# 1x1 transparent PNG (tracking pixel).
PIXEL = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


class EmailTemplateViewSet(viewsets.ModelViewSet):
    queryset = EmailTemplate.objects.all()
    serializer_class = EmailTemplateSerializer
    permission_classes = [IsAuthenticated, CanModify]
    search_fields = ["name", "subject", "body_html"]
    filterset_fields = ["category", "is_active"]
    ordering = ["name"]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"])
    def duplicate(self, request, pk=None):
        template = self.get_object()
        template.pk = None
        template.name = f"{template.name} (copy)"
        template.slug = ""
        template.is_default = False
        template.save()
        return Response(EmailTemplateSerializer(template).data,
                        status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def variables(self, request):
        from .render import available_variables

        return Response(available_variables())

    @action(detail=False, methods=["post"])
    def render_preview(self, request):
        """Render a template with a lead's context (no sending)."""
        from .render import render_variables
        from .sender import build_context

        template_id = request.data.get("template_id")
        lead_id = request.data.get("lead_id")
        template = EmailTemplate.objects.filter(pk=template_id).first()
        lead = Lead.objects.filter(pk=lead_id).first()
        if template is None:
            return Response({"detail": "Template not found."},
                            status=status.HTTP_404_NOT_FOUND)
        context = build_context(lead) if lead else {}
        return Response({
            "subject": render_variables(template.subject, context),
            "body_html": render_variables(template.body_html, context),
            "context": context,
        })


class FollowUpSequenceViewSet(viewsets.ModelViewSet):
    queryset = FollowUpSequence.objects.prefetch_related("steps").all()
    serializer_class = FollowUpSequenceSerializer
    permission_classes = [IsAuthenticated, CanModify]
    search_fields = ["name"]
    filterset_fields = ["is_active"]

    @action(detail=False, methods=["post"])
    def seed_defaults(self, request):
        """Create the standard sequence: day 0, +3, +7, +14."""
        sequence, _ = FollowUpSequence.objects.get_or_create(
            name="Standard (day 0 / +3 / +7 / +14)",
            defaults={"description": "Initial email plus three follow-ups."},
        )
        defaults = [(1, 3, "Quick follow-up"), (2, 7, "Second nudge"),
                    (3, 14, "Last check-in")]
        created = 0
        for order, days, subject in defaults:
            step, new = FollowUpStep.objects.get_or_create(
                sequence=sequence, order=order,
                defaults={"delay_days": days, "subject": subject,
                          "condition": FollowUpStep.Condition.NO_REPLY},
            )
            created += int(new)
        return Response({"sequence_id": sequence.pk, "steps_created": created})


class FollowUpStepViewSet(viewsets.ModelViewSet):
    queryset = FollowUpStep.objects.select_related("template").all()
    serializer_class = FollowUpStepSerializer
    permission_classes = [IsAuthenticated, CanModify]
    filterset_fields = ["sequence"]
    ordering = ["sequence", "order"]


class EmailMessageViewSet(viewsets.ModelViewSet):
    queryset = EmailMessage.objects.select_related("lead", "campaign", "template").all()
    permission_classes = [IsAuthenticated, CanModify]
    filterset_fields = ["campaign", "lead", "status", "step_number", "is_ai_generated"]
    search_fields = ["to_email", "subject", "body_html"]
    ordering_fields = ["created_at", "scheduled_at", "sent_at"]
    ordering = ["-created_at"]

    def get_serializer_class(self):
        return EmailMessageDetailSerializer if self.action == "retrieve" \
            else EmailMessageListSerializer

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated,
                                                               IsManagerOrAdmin])
    def send_now(self, request, pk=None):
        """Send a queued message immediately (respects the daily quota)."""
        from .sender import send_message

        message = self.get_object()
        result = send_message(message, actor=request.user)
        return Response(result)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated,
                                                               IsManagerOrAdmin])
    def cancel(self, request, pk=None):
        message = self.get_object()
        if message.status in {EmailMessage.Status.SENT, EmailMessage.Status.CANCELLED}:
            return Response({"detail": f"Message is already {message.status}."},
                            status=status.HTTP_400_BAD_REQUEST)
        message.mark_cancelled("Cancelled by user")
        return Response({"status": message.status})

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated,
                                                               IsManagerOrAdmin])
    def requeue(self, request, pk=None):
        message = self.get_object()
        if message.status != EmailMessage.Status.FAILED:
            return Response({"detail": "Only failed messages can be requeued."},
                            status=status.HTTP_400_BAD_REQUEST)
        message.status = EmailMessage.Status.QUEUED
        message.scheduled_at = timezone.now()
        message.last_error = ""
        message.save(update_fields=["status", "scheduled_at", "last_error", "updated_at"])
        return Response({"status": message.status})

    @action(detail=False, methods=["post"], permission_classes=[IsAuthenticated,
                                                                IsManagerOrAdmin])
    def run_queue(self, request):
        from .tasks import send_due_emails

        result = send_due_emails()
        return Response(result)


class EmailEventViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = EmailEvent.objects.select_related("message").all()
    serializer_class = EmailEventSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["message", "type"]
    ordering = ["-occurred_at"]


# ---------------------------------------------------------------------------
# Quota / usage
# ---------------------------------------------------------------------------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def email_usage(request):
    """Today's counter plus a short history (Dashboard + Email pages)."""
    days = int(request.query_params.get("days", 14) or 14)
    from datetime import timedelta

    from django.utils import timezone as tz

    today = tz.localdate()
    history = list(
        DailyEmailUsage.objects.filter(
            date__gte=today - timedelta(days=days)
        ).order_by("-date")
    )
    return Response({
        "today": DailyEmailQuota.status(),
        "history": DailyEmailUsageSerializer(history, many=True).data,
        "capacity_next_days": DailyEmailQuota.schedule_capacity(7),
        "smtp_limit": DailyEmailQuota.smtp_limit(),
        "hard_cap": DailyEmailQuota.hard_cap(),
    })


class DailyEmailUsageViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DailyEmailUsage.objects.all()
    serializer_class = DailyEmailUsageSerializer
    permission_classes = [IsAuthenticated]
    ordering = ["-date"]


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsManagerOrAdmin])
def send_now(request):
    """Compose and (optionally) send an email to one lead right now."""
    from .sender import compose_message, send_message

    serializer = SendNowSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    lead = get_object_or_404(Lead, pk=data["lead_id"])
    template = EmailTemplate.objects.filter(pk=data.get("template_id")).first()
    campaign = None
    if data.get("campaign_id"):
        from apps.campaigns.models import Campaign

        campaign = Campaign.objects.filter(pk=data["campaign_id"]).first()
        template = template or campaign.template if campaign else template

    message = compose_message(
        lead=lead, template=template, campaign=campaign,
        subject=data.get("subject", ""), body_html=data.get("body_html", ""),
        use_ai=data.get("use_ai", True), actor=request.user,
    )
    if not data.get("send_immediately"):
        message.save()
        return Response({"queued": True, "message_id": message.pk,
                         "subject": message.subject}, status=status.HTTP_201_CREATED)

    message.save()
    result = send_message(message, actor=request.user)
    result["message_id"] = message.pk
    return Response(result)


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsManagerOrAdmin])
def smtp_test(request):
    """Send a transactional test email (does not consume the marketing quota)."""
    from .tasks import send_test_email

    serializer = TestEmailSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    result = send_test_email(
        serializer.validated_data["to_email"],
        serializer.validated_data.get("subject", "SMTP test"),
        serializer.validated_data.get("body", ""),
    )
    return Response(result)


# ---------------------------------------------------------------------------
# Public tracking endpoints (no authentication - token based)
# ---------------------------------------------------------------------------
def _client_ip(request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


@api_view(["GET"])
@permission_classes([AllowAny])
def track_open(request, uid: str):
    """Record an open *only* when the pixel is actually fetched."""
    throttle = ScopedRateThrottle()
    throttle.scope = "tracking"
    message = EmailMessage.objects.filter(uid=uid).first()
    if message is not None and message.status == EmailMessage.Status.SENT:
        first_open = message.opened_at is None
        message.open_count = (message.open_count or 0) + 1
        if first_open:
            message.opened_at = timezone.now()
        message.save(update_fields=["open_count", "opened_at", "updated_at"])
        EmailEvent.objects.create(
            message=message, type=EmailEvent.Type.OPENED,
            ip_address=_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:400],
        )
        if first_open:
            if message.lead_id:
                message.lead.log_activity(
                    type="EMAIL_OPENED", title="Email opened",
                    description=message.subject,
                    metadata={"message_id": message.pk},
                )
            if message.campaign_id:
                from apps.campaigns.models import Campaign

                Campaign.objects.filter(pk=message.campaign_id).update(
                    total_opened=F("total_opened") + 1
                )
    return HttpResponse(PIXEL, content_type="image/png")


@api_view(["GET"])
@permission_classes([AllowAny])
def track_click(request, uid: str):
    """Record a click and redirect to the original URL."""
    from urllib.parse import unquote

    target = unquote(request.GET.get("u", "") or "")
    message = EmailMessage.objects.filter(uid=uid).first()
    if message is not None:
        first_click = message.clicked_at is None
        message.click_count = (message.click_count or 0) + 1
        if first_click:
            message.clicked_at = timezone.now()
        message.save(update_fields=["click_count", "clicked_at", "updated_at"])
        EmailEvent.objects.create(
            message=message, type=EmailEvent.Type.CLICKED, url=target[:2000],
            ip_address=_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:400],
        )
        if first_click:
            if message.lead_id:
                message.lead.log_activity(
                    type="EMAIL_CLICKED", title="Link clicked",
                    description=target[:200], metadata={"message_id": message.pk},
                )
            if message.campaign_id:
                from apps.campaigns.models import Campaign

                Campaign.objects.filter(pk=message.campaign_id).update(
                    total_clicked=F("total_clicked") + 1
                )
    if not target or not target.startswith(("http://", "https://")):
        return HttpResponse("", status=204)
    return HttpResponseRedirect(target)


# ---------------------------------------------------------------------------
# Unsubscribe
# ---------------------------------------------------------------------------
@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def unsubscribe(request, token: str):
    """One-click unsubscribe (GET shows details, POST performs it).

    POST is idempotent: repeating it simply returns the current state.
    """
    from apps.suppression.services import add_suppression

    message = EmailMessage.objects.filter(unsubscribe_token=token).select_related(
        "lead", "campaign"
    ).first()
    if message is None:
        return Response({"detail": "This unsubscribe link is not valid."},
                        status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        return Response({
            "email": message.to_email,
            "company": message.lead.company_name if message.lead_id else "",
            "subject": message.subject,
            "sent_at": message.sent_at,
            "already_unsubscribed": bool(message.unsubscribed_at),
        })

    now = timezone.now()
    if not message.unsubscribed_at:
        message.unsubscribed_at = now
        message.save(update_fields=["unsubscribed_at", "updated_at"])
        EmailEvent.objects.create(message=message, type=EmailEvent.Type.UNSUBSCRIBED)

    # 1. Suppress globally --------------------------------------------------
    add_suppression(
        message.to_email, reason="UNSUBSCRIBED", source="UNSUBSCRIBE_LINK",
        note="Unsubscribed from a marketing email", lead=message.lead,
        email_message=message,
    )

    # 2. Stop every queued email for this address --------------------------
    EmailMessage.objects.filter(
        to_email__iexact=message.to_email,
        status__in=[EmailMessage.Status.QUEUED, EmailMessage.Status.PROCESSING],
    ).update(status=EmailMessage.Status.CANCELLED, cancelled_at=now)

    # 3. Update the lead ----------------------------------------------------
    if message.lead_id:
        Lead.objects.filter(pk=message.lead_id).update(
            unsubscribed_at=now,
            email_status=EmailStatus.UNSUBSCRIBED,
            lead_status=LeadStatus.UNSUBSCRIBED,
            is_blocked=True,
            blocked_reason="Unsubscribed",
            next_follow_up_at=None,
        )
        lead = Lead.objects.filter(pk=message.lead_id).first()
        if lead:
            lead.log_activity(
                type="UNSUBSCRIBED", title="Unsubscribed",
                description=f"Unsubscribed from '{message.subject}'",
                metadata={"message_id": message.pk},
            )

    # 4. Stop campaign membership -------------------------------------------
    if message.campaign_lead_id:
        from apps.campaigns.models import CampaignLead

        CampaignLead.objects.filter(pk=message.campaign_lead_id).update(
            status=CampaignLead.Status.UNSUBSCRIBED, stopped_reason="Unsubscribed",
            next_follow_up_at=None,
        )

    log_audit(action="UNSUBSCRIBED", entity_type="email_message", entity_id=message.pk,
              description=f"{message.to_email} unsubscribed",
              metadata={"campaign_id": message.campaign_id, "lead_id": message.lead_id})
    return Response({
        "unsubscribed": True,
        "email": message.to_email,
        "message": "You have been unsubscribed and will not receive further emails.",
    })
