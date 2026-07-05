from decimal import Decimal
from datetime import date

from django.db import transaction

from ..models import Immobilisation, PlanAmortissement
from .ecriture_service import EcritureService


class AmortissementService:
    """Gestion des amortissements."""

    @staticmethod
    def creer_immobilisation(code, libelle, type_immo, date_acquisition,
                             valeur_originale, duree_ans, compte_immo,
                             compte_amort, compte_charge, valeur_residuelle=0):
        return Immobilisation.objects.create(
            code=code, libelle=libelle, type_immobilisation=type_immo,
            date_acquisition=date_acquisition,
            valeur_originale=valeur_originale,
            valeur_residuelle=valeur_residuelle,
            duree_ans=duree_ans,
            compte_immobilisation=compte_immo,
            compte_amortissement=compte_amort,
            compte_charge=compte_charge,
        )

    @staticmethod
    def generer_plan(immobilisation):
        PlanAmortissement.objects.filter(immobilisation=immobilisation).delete()

        for annee in range(immobilisation.duree_ans):
            for mois in range(1, 13):
                mois_periode = immobilisation.date_acquisition.month + mois - 1
                annee_periode = immobilisation.date_acquisition.year + annee + (mois_periode // 12)
                mois_periode = (mois_periode % 12) or 12
                periode = date(annee_periode, mois_periode, 1)

                cumul = immobilisation.amortissement_mensuel * (annee * 12 + mois)
                if cumul > immobilisation.base_amortissable:
                    cumul = immobilisation.base_amortissable

                if annee * 12 + mois > immobilisation.duree_ans * 12:
                    break

                PlanAmortissement.objects.create(
                    immobilisation=immobilisation,
                    periode=periode,
                    montant=min(immobilisation.amortissement_mensuel,
                                immobilisation.base_amortissable - cumul + immobilisation.amortissement_mensuel),
                    amortissement_cumule=cumul,
                    valeur_nette=immobilisation.valeur_originale - cumul,
                )

    @staticmethod
    @transaction.atomic
    def generer_ecritures_amortissement(periode=None, user=None):
        if periode is None:
            periode = date.today().replace(day=1)

        plans = PlanAmortissement.objects.filter(
            periode=periode, ecriture_generee=False,
        ).select_related("immobilisation")

        ecritures = []
        for plan in plans:
            ecriture = EcritureService.creer_ecriture_amortissement(plan, user=user)
            ecritures.append(ecriture)
        return ecritures
