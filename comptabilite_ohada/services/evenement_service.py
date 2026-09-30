from django.db import transaction
from django.utils import timezone

from ..models import EvenementMetier, RegleEvenementComptable
from ..rules import moteur
from .ecriture_service import EcritureService


JOURNAUX_PAR_CODE = {
    "VN": ("Ventes", "VENTES"),
    "AC": ("Achats", "ACHATS"),
    "BQ": ("Banque", "BANQUE"),
    "CS": ("Caisse", "CAISSE"),
    "TR": ("Trésorerie", "BANQUE"),
    "PA": ("Paie", "PAIE"),
    "ST": ("Stock", "STOCK"),
    "INV": ("Immobilisations", "IMMO"),
    "OD": ("Opérations diverses", "OD"),
}


class EvenementService:
    """Inbox idempotente transformant un événement métier en écriture comptable."""

    @staticmethod
    def _regle_pour(entreprise_id, type_evenement):
        regle = RegleEvenementComptable.objects.filter(
            entreprise_id=entreprise_id or "",
            type_evenement=type_evenement,
            actif=True,
        ).first()
        if regle:
            return regle
        return RegleEvenementComptable.objects.filter(
            entreprise_id="",
            type_evenement=type_evenement,
            actif=True,
        ).first()

    @classmethod
    @transaction.atomic
    def recevoir(
        cls,
        *,
        entreprise_id,
        type_evenement,
        source_system,
        idempotency_key,
        payload,
        source_type="",
        source_id="",
        user=None,
    ):
        entreprise_id = entreprise_id or ""
        evenement, created = EvenementMetier.objects.get_or_create(
            entreprise_id=entreprise_id,
            idempotency_key=idempotency_key,
            defaults={
                "type_evenement": type_evenement,
                "source_system": source_system,
                "source_type": source_type or "",
                "source_id": str(source_id or ""),
                "payload": payload or {},
            },
        )
        if not created:
            return evenement, False

        regle_mapping = cls._regle_pour(entreprise_id, type_evenement)
        if regle_mapping is None:
            evenement.statut = "IGNORE"
            evenement.processed_at = timezone.now()
            evenement.save(update_fields=["statut", "processed_at"])
            return evenement, True

        try:
            contexte = dict(payload or {})
            contexte.update(regle_mapping.configuration or {})
            resultats = moteur.appliquer(regle_mapping.code_regle, **contexte)
            if not resultats:
                evenement.statut = "IGNORE"
                evenement.processed_at = timezone.now()
                evenement.save(update_fields=["statut", "processed_at"])
                return evenement, True

            resultat = resultats[0]
            journal_libelle, journal_type = JOURNAUX_PAR_CODE.get(
                resultat.journal_code,
                (resultat.journal_code, "OD"),
            )
            journal = EcritureService.get_or_create_journal(
                resultat.journal_code,
                journal_libelle,
                journal_type,
                entreprise_id,
            )

            dimensions = contexte.get("dimensions") or {}
            lignes = []
            for ligne in resultat.lignes:
                lignes.append({
                    "compte": EcritureService.get_compte(ligne.compte_code, entreprise_id),
                    "debit": ligne.debit,
                    "credit": ligne.credit,
                    "libelle": ligne.libelle or resultat.libelle,
                    "dimensions": dimensions,
                })

            ecriture = EcritureService.creer_ecriture(
                reference=resultat.reference,
                date_ecriture=resultat.date_ecriture,
                libelle=resultat.libelle,
                journal=journal,
                lignes=lignes,
                user=user,
                entreprise_id=entreprise_id,
                source_system=source_system,
                source_type=source_type or type_evenement,
                source_id=str(source_id or ""),
                source_reference=str(contexte.get("source_reference") or ""),
                idempotency_key=idempotency_key,
                metadata={
                    "event_type": type_evenement,
                    "event_id": evenement.pk,
                },
            )

            evenement.ecriture = ecriture
            evenement.statut = "TRAITE"
            evenement.processed_at = timezone.now()
            evenement.save(update_fields=["ecriture", "statut", "processed_at"])
            return evenement, True
        except Exception as exc:
            evenement.statut = "ERREUR"
            evenement.erreur = str(exc)
            evenement.processed_at = timezone.now()
            evenement.save(update_fields=["statut", "erreur", "processed_at"])
            raise
