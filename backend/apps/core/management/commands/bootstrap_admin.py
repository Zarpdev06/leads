"""Create or update the administrator account.

    python manage.py bootstrap_admin --email admin@example.com --password '…'
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import DatabaseError

from apps.accounts.models import User


class Command(BaseCommand):
    help = "Create or update the platform administrator."

    def add_arguments(self, parser):
        parser.add_argument("--email", default="admin@example.com")
        parser.add_argument("--password", default=None,
                            help="Defaults to the DJANGO_ADMIN_PASSWORD env var or 'AdminPass123!'")
        parser.add_argument("--first-name", default="Platform")
        parser.add_argument("--last-name", default="Admin")

    def handle(self, *args, **options):
        from django.conf import settings

        password = options["password"] or getattr(settings, "ADMIN_DEFAULT_PASSWORD", "AdminPass123!")
        user, created = User.objects.get_or_create(
            email=options["email"].lower(),
            defaults={
                "first_name": options["first_name"],
                "last_name": options["last_name"],
                "role": User.Role.ADMIN,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        user.role = User.Role.ADMIN
        user.is_staff = True
        user.is_superuser = True
        user.set_password(password)
        user.save()
        self.stdout.write(
            self.style.SUCCESS(
                f"{'Created' if created else 'Updated'} admin {user.email} "
                f"(password: {password}) - change it after the first login."
            )
        )
