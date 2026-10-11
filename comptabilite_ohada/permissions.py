from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

from .models import EcritureComptable


def get_all_compta_permissions():
    """Retourne les permissions personnalisées du module comptabilité."""
    ct = ContentType.objects.get_for_model(EcritureComptable)
    return Permission.objects.filter(
        Q(content_type=ct) & Q(codename__startswith="compta_")
    )


def has_compta_permission(user, permission_codename):
    # Host must additionally check active enterprise membership and local role.
    return bool(user.is_authenticated and user.is_active and (
        user.user_permissions.filter(content_type__app_label='comptabilite_ohada', codename=permission_codename).exists()
        or user.groups.filter(permissions__content_type__app_label='comptabilite_ohada', permissions__codename=permission_codename).exists()
    ))


from rest_framework.permissions import BasePermission


class LegacyAPIUnavailable(BasePermission):
    message = 'API OHADA historique désactivée ; adaptateur autorisé par entreprise requis.'

    def has_permission(self, request, view):
        return False

