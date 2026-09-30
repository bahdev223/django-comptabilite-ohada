from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from rest_framework.permissions import BasePermission, SAFE_METHODS

from .models import AccesEntrepriseComptable, EcritureComptable
from .tenant import resolve_entreprise_id


def get_all_compta_permissions():
    """Retourne les permissions personnalisées du module comptabilité."""
    ct = ContentType.objects.get_for_model(EcritureComptable)
    return Permission.objects.filter(
        Q(content_type=ct) & Q(codename__startswith="compta_")
    )


def has_compta_permission(user, permission_codename):
    if user.is_superuser or user.is_staff:
        return True
    return (
        user.user_permissions.filter(codename=permission_codename).exists()
        or user.groups.filter(permissions__codename=permission_codename).exists()
    )


class AccountingTenantPermission(BasePermission):
    """Rôles standalone minimaux sans imposer ce modèle aux projets hôtes."""

    validation_actions = {"valider", "annuler", "cloturer", "rouvrir"}

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False):
            return True

        # Un projet hôte peut fournir son propre contexte d'entreprise.
        if str(getattr(user, "entreprise_id", "") or ""):
            return True

        entreprise_id = resolve_entreprise_id(request)
        if not entreprise_id:
            # Compatibilité mono-entreprise historique.
            return True

        access = AccesEntrepriseComptable.objects.filter(
            user=user,
            entreprise__code=entreprise_id,
            actif=True,
            entreprise__actif=True,
        ).first()
        if access is None:
            return False

        if request.method in SAFE_METHODS:
            return True
        if access.role in ("ADMIN", "COMPTABLE"):
            return True
        if access.role == "VALIDATEUR" and getattr(view, "action", None) in self.validation_actions:
            return True
        return False
