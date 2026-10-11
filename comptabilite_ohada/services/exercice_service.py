"""Fiscal year and ledger validation: strict tenant scope, period locks and reversal."""
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from ..models import (
    EcritureComptable, ExerciceComptable, LigneEcritureComptable,
)
from ..signals.ecriture import ecriture_validee
from ..tenancy import (
    allow_ledger_validation, check_owned, require_tenant,
)
from .ecriture_service import EcritureService


class ExerciceService:
    """Fiscal years are per enterprise, without shared global fallbacks."""

    @staticmethod
    @transaction.atomic
    def creer(code, date_debut, date_fin, entreprise_id=None):
        tenant = require_tenant(entreprise_id)
        if not code or date_debut >= date_fin:
            raise ValidationError("Code ou période d'exercice incorrecte.")
        if ExerciceComptable.objects.filter(
            entreprise_id=tenant,
            date_debut__lte=date_fin,
            date_fin__gte=date_debut,
        ).exists():
            raise ValidationError("Un exercice de cette entreprise couvre déjà cette période.")
        return ExerciceComptable.objects.create(
            entreprise_id=tenant, code=code,
            date_debut=date_debut, date_fin=date_fin,
        )

    @staticmethod
    def cloturer(exercice, user=None, entreprise_id=None):
        # Closing and reopening need independently reviewed SYSCOHADA carry-forward,
        # concurrent reconciliation and audit policies. Do not freeze a year with
        # the legacy result-to-capital shortcut or without a reviewed closing plan.
        check_owned(exercice, entreprise_id, what="Exercice")
        raise ValidationError(
            "Clôture désactivée jusqu'à validation du processus SYSCOHADA "
            "et de l'autorité Cloud/Local."
        )

    @staticmethod
    def rouvrir(exercice, entreprise_id=None):
        check_owned(exercice, entreprise_id, what="Exercice")
        raise ValidationError(
            "Réouverture désactivée jusqu'à définition de la procédure d'audit."
        )


class ValidationService:
    """All validation transitions are coordinated with the fiscal-year lock."""

    @staticmethod
    @transaction.atomic
    def valider_ecriture(ecriture, user=None, entreprise_id=None):
        tenant = require_tenant(entreprise_id)
        check_owned(ecriture, tenant, what="Écriture")
        # Same lock order as EcritureService.creer_ecriture.
        exercice = ExerciceComptable.objects.select_for_update().get(
            pk=ecriture.exercice_id, entreprise_id=tenant,
        )
        entry = EcritureComptable.objects.select_for_update().get(
            pk=ecriture.pk, entreprise_id=tenant,
        )
        if entry.validee:
            raise ValidationError("Écriture déjà validée.")
        check_owned(entry.journal, tenant, what="Journal")
        if not entry.journal.actif or exercice.cloture:
            raise ValidationError("Journal inactif ou exercice clôturé.")
        if not exercice.date_debut <= entry.date_ecriture <= exercice.date_fin:
            raise ValidationError("Date d'écriture hors exercice.")

        lines = list(
            LigneEcritureComptable.objects.select_related("compte")
            .filter(ecriture=entry)
        )
        if len(lines) < 2:
            raise ValidationError("Une écriture nécessite au moins deux lignes.")

        total_debit, total_credit = Decimal("0.00"), Decimal("0.00")
        for index, line in enumerate(lines, start=1):
            check_owned(line.compte, tenant, what=f"Compte de ligne {index}")
            if not line.compte.actif or not line.compte.est_mouvement:
                raise ValidationError("Compte non mouvementable ou inactif.")
            debit, credit = line.debit, line.credit
            if (debit > 0) == (credit > 0) or debit < 0 or credit < 0:
                raise ValidationError("Ligne à montant non positif ou sur deux sens.")
            total_debit += debit
            total_credit += credit

        if total_debit != total_credit or total_debit <= 0:
            raise ValidationError(
                f"Écriture déséquilibrée : débit {total_debit}, crédit {total_credit}."
            )

        with allow_ledger_validation():
            entry.validee = True
            entry.date_validation = timezone.now()
            entry.save(update_fields=["validee", "date_validation"])

        # Signalling after commit prevents side effects from a rolled-back ledger.
        transaction.on_commit(
            lambda: ecriture_validee.send(
                sender=ValidationService,
                instance=entry,
                lignes=lines,
                user=user,
            )
        )
        ecriture.validee = entry.validee
        ecriture.date_validation = entry.date_validation
        return entry

    @staticmethod
    @transaction.atomic
    def annuler_ecriture(ecriture, user=None, raison="", entreprise_id=None):
        tenant = require_tenant(entreprise_id)
        check_owned(ecriture, tenant, what="Écriture")
        original = EcritureComptable.objects.select_for_update().get(
            pk=ecriture.pk, entreprise_id=tenant
        )
        if not original.validee:
            raise ValidationError("Seules les écritures validées peuvent être contrepassées.")
        today = timezone.localdate()
        exercice_actuel = EcritureService.get_exercice(today, entreprise_id=tenant)
        if exercice_actuel is None:
            raise ValidationError("Aucun exercice ouvert pour la contrepassation.")

        lines = []
        for line in original.lignes.select_related("compte").all():
            check_owned(line.compte, tenant, what="Compte de contrepassation")
            lines.append({
                "compte": line.compte,
                "debit": line.credit,
                "credit": line.debit,
                "libelle": f"CONTREPASSATION : {line.libelle or original.libelle}"[:200],
            })
        # Stable reference + (tenant, reference) uniqueness => no repeated reversal.
        return EcritureService.creer_ecriture(
            reference=f"REV-{original.pk}",
            date_ecriture=today,
            libelle=f"Contrepassation {original.reference} : {raison}"[:200],
            journal=original.journal,
            lignes=lines,
            exercice=exercice_actuel,
            piece=original.reference,
            validee=True,
            user=user,
            entreprise_id=tenant,
        )
