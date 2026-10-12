"""Default off; the unsafe bridge cannot be re-enabled."""
from django.conf import settings


def connect_integrations():
    if getattr(settings, 'COMPTABILITE_OHADA', {}).get('COMPTES_INTEGRATION_ENABLED', False):
        from .django_comptes import connect
        connect()
