from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    CompteComptableViewSet, EcritureComptableViewSet,
    JournalComptableViewSet, ExerciceComptableViewSet,
    ConfigurationComptableViewSet, ImmobilisationViewSet,
)

router = DefaultRouter()
router.register(r"comptes", CompteComptableViewSet)
router.register(r"ecritures", EcritureComptableViewSet)
router.register(r"journaux", JournalComptableViewSet)
router.register(r"exercices", ExerciceComptableViewSet)
router.register(r"configurations", ConfigurationComptableViewSet)
router.register(r"immobilisations", ImmobilisationViewSet)

urlpatterns = [
    path("api/comptabilite/", include(router.urls)),
]
