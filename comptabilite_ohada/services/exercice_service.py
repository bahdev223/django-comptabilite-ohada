from decimal import Decimal
from datetime import date, timedelta

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.dateparse import parse_date

from ..models import ExerciceComptable, ConfigurationComptable, EcritureComptable
from ..models import CompteComptable, LigneEcritureComptable
from ..signals.ecriture import exercice_cloture
from .ecriture_service import EcritureService
from .bilan_service import BilanService


class ExerciceService:
    """Gestion des exercices comptables."""

    @staticmethod
    def creer(code, date_debut, date_fin, entreprise_id=""):
        return ExerciceComptable.objects.create(
            code=code, date_debut=date_debut, date_fin=date_fin,
            entreprise_id=entreprise_id or "",
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

        resultat = BilanService.compte_resultat(
            exercice=exercice,
            entreprise_id=exercice.entreprise_id,
        )["resultat_net"]

        # Même avec un résultat net nul, les comptes 6/7/8 ayant mouvement
        # doivent être soldés.
        EcritureService.creer_ecriture_cloture_exercice(
            exercice,
            user=user,
        )

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
    @transaction.atomic
    def rouvrir(exercice, user=None):
        if not exercice.cloture:
            raise ValueError(f"Exercice {exercice.code} est déjà ouvert")

        exercice.cloture = False
        exercice.date_cloture = None
        exercice.save(update_fields=["cloture", "date_cloture"])

        cloture = EcritureComptable.objects.filter(
            exercice=exercice,
            validee=True,
            source_system="comptabilite_ohada",
            source_type="fiscal_closure",
            source_id=str(exercice.pk),
        ).order_by("-created_at").first()
        if cloture and not cloture.reversals.exists():
            ValidationService.annuler_ecriture(
                cloture,
                user=user,
                raison=f"Réouverture exercice {exercice.code}",
            )

        return exercice


class ValidationService:
    """Validation des écritures et des soldes."""

    @staticmethod
    def valider_ecriture(ecriture, user=None):
        if ecriture.validee:
            raise ValueError(f"Écriture {ecriture.reference} déjà validée")
        if ecriture.exercice.cloture:
            raise ValueError("Une écriture d'un exercice clôturé ne peut pas être validée.")
        date_debut = (
            parse_date(ecriture.exercice.date_debut)
            if isinstance(ecriture.exercice.date_debut, str)
            else ecriture.exercice.date_debut
        )
        date_fin = (
            parse_date(ecriture.exercice.date_fin)
            if isinstance(ecriture.exercice.date_fin, str)
            else ecriture.exercice.date_fin
        )
        date_ecriture = (
            parse_date(ecriture.date_ecriture)
            if isinstance(ecriture.date_ecriture, str)
            else ecriture.date_ecriture
        )
        if date_ecriture is None:
            raise ValueError("La date de l'écriture est invalide.")
        if not (date_debut <= date_ecriture <= date_fin):
            raise ValueError("La date de l'écriture est hors de la période de l'exercice.")
        if (
            (ecriture.journal.entreprise_id or "") != (ecriture.entreprise_id or "")
            or (ecriture.exercice.entreprise_id or "") != (ecriture.entreprise_id or "")
        ):
            raise ValueError("Journal, exercice et écriture doivent appartenir à la même entreprise.")

        lignes = list(ecriture.lignes.select_related("compte"))
        if len(lignes) < 2:
            raise ValueError("Une écriture doit contenir au moins deux lignes.")
        for position, ligne in enumerate(lignes, start=1):
            if (ligne.compte.entreprise_id or "") != (ecriture.entreprise_id or ""):
                raise ValueError(f"Ligne {position}: compte d'une autre entreprise.")
            if not ligne.compte.est_mouvement:
                raise ValueError(f"Ligne {position}: compte non mouvementable.")
        if ecriture.total_debit == 0:
            raise ValueError("Une écriture sans montant ne peut pas être validée.")
        if not ecriture.est_equilibree:
            raise ValueError(f"Écriture {ecriture.reference} déséquilibrée "
                             f"(Débit: {ecriture.total_debit}, Crédit: {ecriture.total_credit})")
        ecriture.validee = True
        ecriture.date_validation = timezone.now()
        ecriture.validated_by = (
            user.username if hasattr(user, "username") and user else str(user or "")
        )
        ecriture.save(update_fields=["validee", "date_validation", "validated_by"])
        return ecriture

    @staticmethod
    def annuler_ecriture(ecriture, user=None, raison=""):
        if not ecriture.validee:
            raise ValueError("Seules les écritures validées peuvent être annulées")
        existante = ecriture.reversals.filter(validee=True).order_by("-created_at").first()
        if existante:
            return existante
        journal = ecriture.journal
        ref = f"ANNULE-{ecriture.reference}"[:50]
        lignes_inversees = []
        for l in ecriture.lignes.prefetch_related(
            "affectations_analytiques__dimension",
            "affectations_analytiques__valeur",
        ):
            dimensions = {}
            for affectation in l.affectations_analytiques.all():
                dimensions.setdefault(
                    affectation.dimension.code,
                    [],
                ).append({
                    "code": affectation.valeur.code,
                    "libelle": affectation.valeur.libelle,
                    "external_id": affectation.valeur.external_id,
                    "pourcentage": affectation.pourcentage,
                    "montant": affectation.montant,
                    "metadata": affectation.valeur.metadata,
                })
            lignes_inversees.append({
                "compte": l.compte,
                "debit": l.credit,
                "credit": l.debit,
                "libelle": f"ANNULATION - {l.libelle or ecriture.libelle}",
                "dimensions": dimensions,
            })
        return EcritureService.creer_ecriture(
            reference=ref,
            date_ecriture=ecriture.date_ecriture,
            libelle=f"Annulation de {ecriture.reference} - {raison}",
            journal=journal,
            lignes=lignes_inversees,
            exercice=ecriture.exercice,
            user=user,
            entreprise_id=ecriture.entreprise_id,
            source_system=ecriture.source_system,
            source_type="reversal",
            source_id=str(ecriture.pk),
            source_reference=ecriture.reference,
            metadata={"raison": raison},
            reversal_of=ecriture,
            idempotency_key=f"reversal:{ecriture.pk}",
        )
