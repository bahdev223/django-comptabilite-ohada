from decimal import Decimal
from datetime import date, timedelta

from django.db import transaction, models
from django.db.models import Sum
from django.core.exceptions import ValidationError
from django.conf import settings
from ..tenancy import require_enterprise, require_owned
from django.utils import timezone

from ..models import ExerciceComptable, ConfigurationComptable, EcritureComptable
from ..models import CompteComptable, LigneEcritureComptable
from ..signals.ecriture import exercice_cloture
from .ecriture_service import EcritureService


class ExerciceService:
    """Gestion des exercices comptables."""

    @staticmethod
    def creer(code, date_debut, date_fin, *, entreprise_id=None):
        entreprise_id = require_enterprise(entreprise_id)
        return ExerciceComptable.objects.create(
            entreprise_id=entreprise_id, code=code, date_debut=date_debut, date_fin=date_fin,
        )

    @staticmethod
    @transaction.atomic
    def cloturer(exercice, user=None, *, entreprise_id=None):
        exercice = require_owned(exercice, entreprise_id)
        # The historical shortcut posted annual profit/loss against capital.
        # This is not a reviewed SYSCOHADA closing process, so refuse to close
        # until the authority, control accounts and carry-forward are audited.
        raise ValidationError(
            "Clôture suspendue : procédure SYSCOHADA et autorité Cloud/Local "
            "non encore certifiées."
        )
        exercice = ExerciceComptable.objects.select_for_update().get(pk=exercice.pk)
        if EcritureComptable.objects.filter(entreprise_id=entreprise_id, exercice=exercice, validee=False).exists():
            raise ValidationError("Brouillons à traiter avant clôture.")
        if exercice.cloture:
            raise ValueError(f"Exercice {exercice.code} déjà clôturé")

        # Vérifier équilibre
        ecritures = EcritureComptable.objects.filter(entreprise_id=entreprise_id, exercice=exercice, validee=True)
        for e in ecritures:
            if not e.est_equilibree:
                raise ValueError(f"Écriture {e.reference} déséquilibrée")

        # Calculer le résultat
        lignes = LigneEcritureComptable.objects.filter(ecriture__in=ecritures)
        charge_totals = lignes.filter(compte__code__startswith='6').aggregate(d=Sum('debit'), c=Sum('credit'))
        product_totals = lignes.filter(compte__code__startswith='7').aggregate(d=Sum('debit'), c=Sum('credit'))
        total_charges = (charge_totals['d'] or Decimal('0')) - (charge_totals['c'] or Decimal('0'))
        total_produits = (product_totals['c'] or Decimal('0')) - (product_totals['d'] or Decimal('0'))
        resultat = total_produits - total_charges

        # Écriture d'affectation
        if resultat:
            EcritureService.creer_ecriture_cloture_exercice(exercice, resultat, user=user, entreprise_id=entreprise_id)

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
    def rouvrir(exercice, *, entreprise_id=None):
        require_owned(exercice, entreprise_id)
        raise ValidationError('Réouverture suspendue : contrepassation de clôture et autorisation requises.')


class ValidationService:
    """Revalidate persisted rows under fiscal-year and entry locks."""

    @staticmethod
    @transaction.atomic
    def valider_ecriture(ecriture, user=None, *, entreprise_id=None):
        from ..tenancy import require_owned, validate_entry
        ecriture = require_owned(ecriture, entreprise_id)
        ExerciceComptable.objects.select_for_update().get(pk=ecriture.exercice_id)
        ecriture = EcritureComptable.objects.select_for_update().get(pk=ecriture.pk)
        if ecriture.validee:
            raise ValidationError('Écriture déjà validée.')
        lignes = list(ecriture.lignes.values('compte', 'debit', 'credit', 'libelle'))
        for ligne in lignes:
            ligne['compte'] = CompteComptable.objects.filter(pk=ligne['compte']).first()
        validate_entry(ecriture.date_ecriture, ecriture.journal, ecriture.exercice, lignes, entreprise_id)
        ecriture.validee = True
        ecriture.date_validation = timezone.now()
        # Validated under locks above; bypass the model's generic save guard only here.
        models.QuerySet(model=EcritureComptable, using=ecriture._state.db).filter(pk=ecriture.pk, validee=False).update(
            validee=True, date_validation=ecriture.date_validation)
        return ecriture

    @staticmethod
    @transaction.atomic
    def annuler_ecriture(ecriture, user=None, raison='', *, entreprise_id=None, date_operation=None):
        from ..tenancy import require_owned
        ecriture = require_owned(ecriture, entreprise_id)
        ExerciceComptable.objects.select_for_update().get(pk=ecriture.exercice_id)
        ecriture = EcritureComptable.objects.select_for_update().get(pk=ecriture.pk)
        if not ecriture.validee or not raison.strip():
            raise ValidationError('Écriture validée et motif obligatoire pour contrepasser.')
        # Stable source-derived reference; serialized repeat rejects, no mutation of original.
        ref = f'ANNULE-ID-{ecriture.pk}'
        if EcritureComptable.objects.filter(entreprise_id=entreprise_id, reference=ref).exists():
            raise ValidationError('Écriture déjà contrepassée.')
        lignes = [dict(compte=l.compte, debit=l.credit, credit=l.debit,
                       libelle=f'Annulation {ecriture.reference}') for l in ecriture.lignes.select_related('compte')]
        return EcritureService.creer_ecriture(
            reference=ref, date_ecriture=date_operation or timezone.now().date(),
            libelle=f'Annulation de {ecriture.reference} - {raison}',
            journal=ecriture.journal, lignes=lignes, user=user, entreprise_id=entreprise_id,
        )
