from __future__ import annotations

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, username=email, **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("role", User.Role.ADMIN)
        return self._create_user(email, password, **extra)


class User(AbstractUser):
    """Platform user. Email is the login identifier."""

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Administrator"
        MANAGER = "MANAGER", "Manager"
        AGENT = "AGENT", "Sales agent"
        VIEWER = "VIEWER", "Viewer"

    email = models.EmailField("email address", unique=True)
    username = models.CharField(max_length=150, blank=True, default="")
    role = models.CharField(
        max_length=20, choices=Role.choices, default=Role.AGENT, db_index=True
    )
    phone = models.CharField(max_length=40, blank=True, default="")
    job_title = models.CharField(max_length=120, blank=True, default="")
    avatar_url = models.URLField(blank=True, default="")
    timezone_name = models.CharField(max_length=64, default="UTC")
    last_seen_at = models.DateTimeField(null=True, blank=True)
    # Sending identity defaults (can be overridden per campaign)
    signature = models.TextField(blank=True, default="")
    email_signature_html = models.TextField(blank=True, default="")

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        ordering = ("email",)
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self) -> str:
        return self.get_full_name() or self.email

    @property
    def display_name(self) -> str:
        return (self.get_full_name() or "").strip() or self.email.split("@")[0]

    def touch(self) -> None:
        self.last_seen_at = timezone.now()
        self.save(update_fields=["last_seen_at"])

    @property
    def can_manage_campaigns(self) -> bool:
        return self.is_superuser or self.role in {self.Role.ADMIN, self.Role.MANAGER}

    def get_role_display_safe(self) -> str:
        return self.get_role_display()
