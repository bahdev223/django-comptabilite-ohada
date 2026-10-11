"""Unsafe automatic accounting signals are disabled.

Cross-service integrations are owned by the standalone accounting service.
No optional django-comptes import or signal registration takes place.
"""
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def connect_integrations():
    config = getattr(settings, "COMPTABILITE_OHADA", {})
    if config.get("COMPTES_INTEGRATION_ENABLED", False):
        raise ImproperlyConfigured(
            "COMPTES_INTEGRATION_ENABLED is unsafe and no longer supported. "
            "Publish an explicit, tenant-scoped and idempotent accounting event."
        )
    if config.get("STOCK_INTEGRATION_ENABLED", False):
        raise ImproperlyConfigured(
            "STOCK_INTEGRATION_ENABLED is unsupported: use the accounting event API."
        )
