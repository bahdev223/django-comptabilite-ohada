from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token

from .views import (
    CompteComptableViewSet, EcritureComptableViewSet,
    JournalComptableViewSet, ExerciceComptableViewSet,
    ConfigurationComptableViewSet, ImmobilisationViewSet,
    DimensionAnalytiqueViewSet, ValeurAnalytiqueViewSet,
    RegleEvenementComptableViewSet, EvenementMetierViewSet,
    OrganisationComptableViewSet,
    ReleveBancaireViewSet,
    health_view,
)

router = DefaultRouter()
router.register(r"organisations", OrganisationComptableViewSet, basename="organisation")
router.register(r"comptes", CompteComptableViewSet)
router.register(r"ecritures", EcritureComptableViewSet)
router.register(r"journaux", JournalComptableViewSet)
router.register(r"exercices", ExerciceComptableViewSet)
router.register(r"configurations", ConfigurationComptableViewSet)
router.register(r"immobilisations", ImmobilisationViewSet)
router.register(r"releves-bancaires", ReleveBancaireViewSet)
router.register(r"dimensions-analytiques", DimensionAnalytiqueViewSet)
router.register(r"valeurs-analytiques", ValeurAnalytiqueViewSet, basename="valeur-analytique")
router.register(r"regles-evenements", RegleEvenementComptableViewSet)
router.register(r"events", EvenementMetierViewSet)

urlpatterns = [
    path("api/v1/health/", health_view, name="api_health"),
    path("api/v1/auth/token/", obtain_auth_token, name="api_token_auth"),
    # Contrat cible pour les intégrations externes.
    path("api/v1/", include(router.urls)),
    # Compatibilité avec les intégrations historiques du paquet.
    path("api/comptabilite/", include(router.urls)),
]
