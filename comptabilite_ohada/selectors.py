from django.db.models import Sum, Q
from datetime import date, timedelta

from .models import (
    CompteComptable, EcritureComptable, LigneEcritureComptable,
    JournalComptable, ExerciceComptable, Immobilisation,
)
from .services.journal_service import BalanceService, GrandLivreService
from .services.bilan_service import BilanService
from .services.dashboard_service import DashboardService


class ComptabiliteSelector:
    """Requêtes complexes pour la comptabilité."""

    def __init__(self):
        self.balance = BalanceService()
        self.grand_livre = GrandLivreService()
        self.bilan_service = BilanService()
        self.dashboard = DashboardService()

    def compte_detail(self, code):
        return CompteComptable.objects.filter(code=code).first()

    def compte_enfants(self, code_prefix):
        return CompteComptable.objects.filter(code__startswith=code_prefix, actif=True)

    def ecritures_non_validees(self):
        return EcritureComptable.objects.filter(validee=False).order_by("-date_ecriture")

    def ecritures_par_periode(self, debut, fin):
        return EcritureComptable.objects.filter(
            date_ecriture__gte=debut, date_ecriture__lte=fin,
        ).order_by("-date_ecriture")

    def ecritures_par_compte(self, compte_code, exercice=None):
        qs = LigneEcritureComptable.objects.filter(
            compte__code__startswith=compte_code,
            ecriture__validee=True,
        ).select_related("ecriture", "compte")
        if exercice:
            qs = qs.filter(
                ecriture__date_ecriture__gte=exercice.date_debut,
                ecriture__date_ecriture__lte=exercice.date_fin,
            )
        return qs.order_by("ecriture__date_ecriture")

    def immobilisations_actives(self):
        return Immobilisation.objects.filter(statut="ACTIF")

    def immobilisations_avec_plan(self, immo_id):
        return Immobilisation.objects.prefetch_related("plan_amortissement").filter(id=immo_id).first()
