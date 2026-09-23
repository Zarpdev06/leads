from __future__ import annotations

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.views import APIView
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from apps.core.models import log_audit
from apps.core.permissions import IsAdminRole

from .serializers import (
    ChangePasswordSerializer,
    LoginSerializer,
    ProfileUpdateSerializer,
    UserCreateSerializer,
    UserSerializer,
)

User = get_user_model()


class LoginView(APIView):
    """POST {email, password} -> {access, refresh, user}"""
    permission_classes = [AllowAny]
    authentication_classes: list = []
    serializer_class = LoginSerializer

    def post(self, request, *args, **kwargs):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.user
        user.touch()
        log_audit(
            action="LOGIN",
            actor=user,
            entity_type="user",
            entity_id=user.id,
            description=f"{user.email} signed in",
            request=request,
        )
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except Exception:
                pass  # token already invalid / blacklist app disabled
        log_audit(
            action="LOGOUT",
            actor=request.user,
            entity_type="user",
            entity_id=request.user.id,
            request=request,
        )
        return Response({"detail": "Logged out."}, status=status.HTTP_200_OK)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = ProfileUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(request.user).data)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(serializer.validated_data["current_password"]):
            return Response({"detail": "Current password is incorrect."},
                            status=status.HTTP_400_BAD_REQUEST)
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        return Response({"detail": "Password updated."})


class UserViewSet(viewsets.ModelViewSet):
    """User administration (admin only)."""
    queryset = User.objects.all().order_by("email")
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, IsAdminRole]
    search_fields = ["email", "first_name", "last_name"]
    filterset_fields = ["role", "is_active"]
    ordering_fields = ["email", "last_login", "date_joined"]
    ordering = ["email"]

    def get_serializer_class(self):
        return UserCreateSerializer if self.action == "create" else UserSerializer

    def perform_create(self, serializer):
        user = serializer.save()
        log_audit(
            action="SETTINGS_UPDATED",
            actor=self.request.user,
            entity_type="user",
            entity_id=user.id,
            description=f"Created user {user.email}",
            request=self.request,
        )

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def stats(self, request):
        now = timezone.now()
        return Response(
            {
                "total": User.objects.count(),
                "active": User.objects.filter(is_active=True).count(),
                "admins": User.objects.filter(role=User.Role.ADMIN).count(),
                "logged_in_today": User.objects.filter(last_seen_at__date=now.date()).count(),
            }
        )


class RefreshView(TokenRefreshView):
    permission_classes = [AllowAny]


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def bootstrap(request):
    """Single round-trip payload the SPA needs on first paint."""
    from apps.settings.services import public_settings_payload

    return Response(
        {
            "user": UserSerializer(request.user).data,
            "settings": public_settings_payload(),
        }
    )
