from django.conf import settings
from rest_framework.exceptions import PermissionDenied

from .models import AccesEntrepriseComptable, OrganisationComptable


def resolve_entreprise_id(request):
    """Résout le tenant sans dépendre d'un modèle utilisateur particulier.

    Ordre :
    1. attribut user.entreprise_id fourni par un projet hôte ;
    2. header X-Enterprise-ID validé contre les appartenances locales ;
    3. appartenance locale unique ;
    4. chaîne vide pour compatibilité mono-entreprise historique.
    """

    user = request.user
    direct = str(getattr(user, "entreprise_id", "") or "")
    if direct:
        return direct

    requested = str(request.headers.get("X-Enterprise-ID", "") or "").strip()

    if requested:
        if getattr(user, "is_superuser", False):
            if OrganisationComptable.objects.filter(code=requested, actif=True).exists():
                return requested
        if AccesEntrepriseComptable.objects.filter(
            user=user,
            entreprise__code=requested,
            entreprise__actif=True,
            actif=True,
        ).exists():
            return requested
        raise PermissionDenied("Accès refusé à cette entreprise comptable.")

    accesses = AccesEntrepriseComptable.objects.filter(
        user=user,
        entreprise__actif=True,
        actif=True,
    ).select_related("entreprise")

    first = accesses.first()
    if first is None:
        config = getattr(settings, "COMPTABILITE_OHADA", {})
        if config.get("REQUIRE_TENANT_MEMBERSHIP", False):
            raise PermissionDenied("Aucune entreprise comptable n'est associée à cet utilisateur.")
        return ""

    if accesses.count() == 1:
        return first.entreprise.code

    raise PermissionDenied(
        "Plusieurs entreprises sont accessibles. Fournissez le header X-Enterprise-ID."
    )
