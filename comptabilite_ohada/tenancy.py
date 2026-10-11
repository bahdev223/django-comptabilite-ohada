"""Explicit, fail-closed accounting tenant boundaries.

The library never infers an enterprise from a client-controlled header, email,
or a globally selected active company. HTTP hosts must provide an authorized
resolver. Non-HTTP jobs must enter tenant_scope explicitly.
"""
from contextlib import contextmanager
from contextvars import ContextVar

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.module_loading import import_string


_ACTIVE_TENANT = ContextVar("comptabilite_ohada_active_tenant", default=None)


def require_tenant(entreprise_id=None):
    active = _ACTIVE_TENANT.get()
    value = active if entreprise_id is None else entreprise_id
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 255
    ):
        raise ValidationError("entreprise_id explicite et non vide obligatoire.")
    if active is not None and active != value:
        raise ValidationError("Entreprise incompatible avec le contexte comptable.")
    return value


@contextmanager
def tenant_scope(entreprise_id):
    """Scope a trusted server-side operation to one explicitly authorized tenant."""
    tenant = require_tenant(entreprise_id)
    token = _ACTIVE_TENANT.set(tenant)
    try:
        yield tenant
    finally:
        _ACTIVE_TENANT.reset(token)


def check_owned(instance, entreprise_id=None, *, what="Ressource"):
    """Reject a foreign or legacy/unassigned record, even if its PK exists."""
    tenant = require_tenant(entreprise_id)
    if instance is None or getattr(instance, "entreprise_id", None) != tenant:
        raise ValidationError(f"{what} n'appartient pas à l'entreprise sélectionnée.")
    return instance


def resolve_request_tenant(request):
    """Ask the host for a verified user→company membership; never trust a header alone.

    COMPTABILITE_OHADA["TENANT_RESOLVER"] = "host.security.resolve_accounting_tenant"
    The resolver must verify a membership/permission and return the stable company ID,
    or raise PermissionDenied. It may honor a company header ONLY AFTER validation.
    """
    from rest_framework.exceptions import PermissionDenied, NotAuthenticated

    if not request.user or not request.user.is_authenticated:
        raise NotAuthenticated("Authentification obligatoire.")
    config = getattr(settings, "COMPTABILITE_OHADA", {})
    dotted_path = config.get("TENANT_RESOLVER")
    if not dotted_path:
        raise PermissionDenied("Résolveur d'entreprise sécurisé non configuré.")
    try:
        resolver = import_string(dotted_path)
        return require_tenant(resolver(request))
    except (ImportError, ValueError, TypeError, ValidationError) as exc:
        raise PermissionDenied("Impossible de vérifier l'appartenance à l'entreprise.") from exc


_LEDGER_VALIDATION_ALLOWED = ContextVar("comptabilite_ohada_ledger_validation", default=False)


@contextmanager
def allow_ledger_validation():
    """Internal guard used only by ValidationService while holding fiscal locks."""
    token = _LEDGER_VALIDATION_ALLOWED.set(True)
    try:
        yield
    finally:
        _LEDGER_VALIDATION_ALLOWED.reset(token)


def is_ledger_validation_allowed():
    return _LEDGER_VALIDATION_ALLOWED.get()
