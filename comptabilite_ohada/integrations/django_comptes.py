"""Deprecated signal adapter: intentionally disabled (P0 security).

A generic ENCAISSEMENT does not prove an accounting sale, a TRANSFERT never
creates revenue and a generic DECAISSEMENT is not necessarily an expense.
Historic signal subscriptions could double-post transfers.

Accounting events must be explicitly classified, versioned, idempotent and
tenant-authorized by an independent integration service. No signal receiver
is registered here, even when this module is imported.
"""
from django.core.exceptions import ImproperlyConfigured


def connect():
    raise ImproperlyConfigured(
        "L'intégration automatique django-comptes est désactivée : "
        "utiliser un contrat d'événements comptables explicite et idempotent."
    )
