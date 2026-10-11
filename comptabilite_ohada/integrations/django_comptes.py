"""Unsafe legacy signal bridge retired. Use a qualified, idempotent inbox."""
from django.core.exceptions import ImproperlyConfigured


def connect():
    raise ImproperlyConfigured('Pont comptes historique désactivé : qualification et inbox idempotente requises.')
