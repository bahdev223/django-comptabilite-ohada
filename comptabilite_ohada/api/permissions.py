"""Mandatory authenticated accounting permissions (GET included)."""
from rest_framework.permissions import BasePermission, IsAuthenticated


class AccountingModelPermission(BasePermission):
    """DRF DjangoModelPermissions does not require view permission for GET by default."""

    def has_permission(self, request, view):
        model = getattr(view, "model", None)
        if not request.user or not request.user.is_authenticated or model is None:
            return False
        action = getattr(view, "action", None)
        if request.method in ("GET", "HEAD", "OPTIONS"):
            perm = f"view_{model._meta.model_name}"
        elif action == "create":
            perm = f"add_{model._meta.model_name}"
        elif action in ("valider", "annuler"):
            perm = f"change_{model._meta.model_name}"
        else:
            return False
        return request.user.has_perm(f"{model._meta.app_label}.{perm}")
