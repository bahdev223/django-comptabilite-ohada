from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction

from ..models import Immobilisation, PlanAmortissement
from .ecriture_service import EcritureService


class AmortissementService:
    """Gestion des immobilisations et des amortissements."""

    @staticmethod
    @transaction.atomic
    def creer_immobilisation(
        code,
        libelle,
        type_immo,
        date_acquisition,
        valeur_originale,
        duree_ans,
        compte_immo,
        compte_amort,
        compte_charge,
        valeur_residuelle=0,
        entreprise_id="",
    ):
        entreprise_id = entreprise_id or ""
        for compte in (compte_immo, compte_amort, compte_charge):
            if (compte.entreprise_id or "") != entreprise_id:
                raise ValidationError(
                    "Tous les comptes de l'immobilisation doivent appartenir à la même entreprise."
                )

        return Immobilisation.objects.create(
            entreprise_id=entreprise_id,
            code=code,
            libelle=libelle,
            type_immobilisation=type_immo,
            date_acquisition=date_acquisition,
            valeur_originale=valeur_originale,
            valeur_residuelle=valeur_residuelle,
            duree_ans=duree_ans,
            compte_immobilisation=compte_immo,
            compte_amortissement=compte_amort,
            compte_charge=compte_charge,
        )

    @staticmethod
    @transaction.atomic
    def generer_plan(immobilisation):
        """Génère un échéancier mensuel linéaire exact et idempotent."""
        if immobilisation.duree_ans <= 0:
            raise ValidationError("La durée d'amortissement doit être strictement positive.")
        if immobilisation.valeur_originale < 0 or immobilisation.valeur_residuelle < 0:
            raise ValidationError("Les valeurs d'immobilisation doivent être positives.")
        if immobilisation.valeur_residuelle > immobilisation.valeur_originale:
            raise ValidationError(
                "La valeur résiduelle ne peut pas dépasser la valeur d'origine."
            )

        # Ne jamais supprimer un plan déjà comptabilisé.
        if immobilisation.plan_amortissement.filter(ecriture_generee=True).exists():
            raise ValidationError(
                "Le plan contient déjà des échéances comptabilisées et ne peut pas être régénéré."
            )

        immobilisation.plan_amortissement.all().delete()

        total_mois = immobilisation.duree_ans * 12
        base = Decimal(immobilisation.base_amortissable).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        mensualite = (base / Decimal(total_mois)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        cumul = Decimal("0.00")
        base_month_index = (
            immobilisation.date_acquisition.year * 12
            + immobilisation.date_acquisition.month
            - 1
        )

        for index in range(total_mois):
            absolute_month = base_month_index + index
            annee = absolute_month // 12
            mois = absolute_month % 12 + 1
            periode = date(annee, mois, 1)

            if index == total_mois - 1:
                montant = base - cumul
            else:
                montant = min(mensualite, base - cumul)

            montant = montant.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            cumul = (cumul + montant).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            PlanAmortissement.objects.create(
                immobilisation=immobilisation,
                periode=periode,
                montant=montant,
                amortissement_cumule=cumul,
                valeur_nette=(
                    Decimal(immobilisation.valeur_originale) - cumul
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            )

        return immobilisation.plan_amortissement.order_by("periode")

    # Alias explicite utilisé par l'API.
    generer_plan_amortissement = generer_plan

    @staticmethod
    @transaction.atomic
    def comptabiliser_amortissement(immobilisation, user=None, jusqu_a=None):
        """Comptabilise les échéances dues d'une immobilisation."""
        if jusqu_a is None:
            jusqu_a = date.today().replace(day=1)

        plans = immobilisation.plan_amortissement.filter(
            periode__lte=jusqu_a,
            ecriture_generee=False,
        ).order_by("periode")

        ecritures = []
        for plan in plans:
            ecritures.append(
                EcritureService.creer_ecriture_amortissement(plan, user=user)
            )
        return ecritures

    @staticmethod
    @transaction.atomic
    def generer_ecritures_amortissement(periode=None, user=None, entreprise_id=""):
        """Comptabilise toutes les échéances d'une période pour un tenant."""
        if periode is None:
            periode = date.today().replace(day=1)

        plans = PlanAmortissement.objects.filter(
            periode=periode,
            ecriture_generee=False,
            immobilisation__entreprise_id=entreprise_id or "",
        ).select_related("immobilisation")

        ecritures = []
        for plan in plans:
            ecritures.append(
                EcritureService.creer_ecriture_amortissement(plan, user=user)
            )
        return ecritures
