"""Django project configuration package (settings, urls, celery app)."""

from .celery import app as celery_app

__all__ = ("celery_app",)
