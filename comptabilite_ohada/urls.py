from django.urls import path, include
from django.conf import settings

from .views.views_dashboard import DashboardView
from .views.views_ecritures import (
    EcritureListView, EcritureDetailView, EcritureCreateView,
    EcritureUpdateView, EcritureDeleteView, EcritureValiderView,
)
from .views.views_comptes import CompteComptableListView, CompteComptableDetailView
from .views.views_journaux import (
    JournalListView, JournalDetailView, BalanceView, GrandLivreView,
)
from .views.views_bilan import BilanView, CompteResultatView
from .views.views_exercices import (
    ExerciceListView, ExerciceDetailView, ExerciceCreateView,
    ExerciceCloturerView, ExerciceRouvrirView,
)
from .views.views_rapprochement import RapprochementListView, RapprochementDetailView
from .views.views_amortissements import ImmobilisationListView, ImmobilisationDetailView
from .views.views_exports import ExportCSVView

app_name = "comptabilite"

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("ecritures/", EcritureListView.as_view(), name="ecriture_list"),
    path("ecritures/creer/", EcritureCreateView.as_view(), name="ecriture_create"),
    path("ecritures/<int:pk>/", EcritureDetailView.as_view(), name="ecriture_detail"),
    path("ecritures/<int:pk>/modifier/", EcritureUpdateView.as_view(), name="ecriture_update"),
    path("ecritures/<int:pk>/supprimer/", EcritureDeleteView.as_view(), name="ecriture_delete"),
    path("ecritures/<int:pk>/valider/", EcritureValiderView.as_view(), name="ecriture_valider"),
    path("comptes/", CompteComptableListView.as_view(), name="compte_list"),
    path("comptes/<int:pk>/", CompteComptableDetailView.as_view(), name="compte_detail"),
    path("journaux/", JournalListView.as_view(), name="journal_list"),
    path("journaux/<int:pk>/", JournalDetailView.as_view(), name="journal_detail"),
    path("balance/", BalanceView.as_view(), name="balance"),
    path("grand-livre/", GrandLivreView.as_view(), name="grand_livre"),
    path("bilan/", BilanView.as_view(), name="bilan"),
    path("compte-resultat/", CompteResultatView.as_view(), name="compte_resultat"),
    path("exercices/", ExerciceListView.as_view(), name="exercice_list"),
    path("exercices/creer/", ExerciceCreateView.as_view(), name="exercice_create"),
    path("exercices/<int:pk>/", ExerciceDetailView.as_view(), name="exercice_detail"),
    path("exercices/<int:pk>/cloturer/", ExerciceCloturerView.as_view(), name="exercice_cloturer"),
    path("exercices/<int:pk>/rouvrir/", ExerciceRouvrirView.as_view(), name="exercice_rouvrir"),
    path("immobilisations/", ImmobilisationListView.as_view(), name="immobilisation_list"),
    path("immobilisations/<int:pk>/", ImmobilisationDetailView.as_view(), name="immobilisation_detail"),
    path("rapprochement/", RapprochementListView.as_view(), name="rapprochement_list"),
    path("rapprochement/<int:pk>/", RapprochementDetailView.as_view(), name="rapprochement_detail"),
    path("exports/", ExportCSVView.as_view(), name="exports"),
]

if getattr(settings, "COMPTABILITE_OHADA", {}).get("API_ENABLED", True):
    urlpatterns += [
        path("", include("comptabilite_ohada.api.urls")),
    ]
