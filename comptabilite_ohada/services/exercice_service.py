from decimal import Decimal
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

from ..models import ExerciceComptable, ConfigurationComptable, EcritureComptable
from ..models import CompteComptable, LigneEcritureComptable
from ..signals.ecriture import exercice_cloture
from .ecriture_service import EcritureService


class ExerciceService:
    """Gestion des exercices comptables."""

    @staticmethod
    def creer(code, date_debut, date_fin):
        return ExerciceComptable.objects.create(
            code=code, date_debut=date_debut, date_fin=date_fin,
        )

    @staticmethod
    @transaction.atomic
    def cloturer(exercice, user=None):
        if exercice.cloture:
            raise ValueError(f"Exercice {exercice.code} déjà clôturé")

        # Vérifier équilibre
        ecritures = EcritureComptable.objects.filter(exercice=exercice, validee=True)
        for e in ecritures:
            if not e.est_equilibree:
                raise ValueError(f"Écriture {e.reference} déséquilibrée")

        # Calculer le résultat
        lignes = LigneEcritureComptable.objects.filter(ecriture__in=ecritures)
        total_charges = lignes.filter(compte__code__startswith="6").aggregate(
            t=Sum("debit")
        )["t"] or Decimal("0.00")
        total_produits = lignes.filter(compte__code__startswith="7").aggregate(
            t=Sum("credit")
        )["t"] or Decimal("0.00")
        resultat = total_produits - total_charges

        # Écriture d'affectation
        EcritureService.creer_ecriture_cloture_exercice(exercice, resultat, user=user)

        exercice.cloture = True
        exercice.date_cloture = timezone.now().date()
        exercice.save()

        exercice_cloture.send(
            sender=ExerciceService,
            instance=exercice,
            resultat=resultat,
            user=user,
        )

        return exercice

    @staticmethod
    def rouvrir(exercice):
        if not exercice.cloture:
            raise ValueError(f"Exercice {exercice.code} est déjà ouvert")
        exercice.cloture = False
        exercice.date_cloture = None
        exercice.save()
        return exercice


class ValidationService:
    """Validation des écritures et des soldes."""

    @staticmethod
    def valider_ecriture(ecriture, user=None):
        if ecriture.validee:
            raise ValueError(f"Écriture {ecriture.reference} déjà validée")
        if not ecriture.est_equilibree:
            raise ValueError(f"Écriture {ecriture.reference} déséquilibrée "
                             f"(Débit: {ecriture.total_debit}, Crédit: {ecriture.total_credit})")
        ecriture.validee = True
        ecriture.date_validation = timezone.now()
        ecriture.save()
        return ecriture

    @staticmethod
    def annuler_ecriture(ecriture, user=None, raison=""):
        if not ecriture.validee:
            raise ValueError("Seules les écritures validées peuvent être annulées")
        journal = ecriture.journal
        ref = f"ANNULE-{ecriture.reference}"
        lignes_inversees = []
        for l in ecriture.lignes.all():
            lignes_inversees.append({
                "compte": l.compte,
                "debit": l.credit,
                "credit": l.debit,
                "libelle": f"ANNULATION - {l.libelle or ecriture.libelle}",
            })
        EcritureService.creer_ecriture(
            reference=ref,
            date_ecriture=timezone.now().date(),
            libelle=f"Annulation de {ecriture.reference} - {raison}",
            journal=journal,
            lignes=lignes_inversees,
            exercice=ecriture.exercice,
            user=user,
        )
