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
    if user.is_superuser or user.is_staff:
        return True
    return (
        user.user_permissions.filter(codename=permission_codename).exists()
        or user.groups.filter(permissions__codename=permission_codename).exists()
    )
