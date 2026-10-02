import json
from decimal import Decimal

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date

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
    "CL": ("Clôture", "OD"),
}


class EvenementService:
    """Inbox idempotente transformant un événement métier en écriture comptable."""

    @staticmethod
    def _payload_stockable(payload):
        return json.loads(json.dumps(payload or {}, cls=DjangoJSONEncoder))

    @staticmethod
    def _contexte_regle(payload):
        contexte = dict(payload or {})
        if isinstance(contexte.get("date"), str):
            parsed = parse_date(contexte["date"])
            if parsed is not None:
                contexte["date"] = parsed
        if isinstance(contexte.get("montant"), str):
            contexte["montant"] = Decimal(contexte["montant"])
        return contexte

    @staticmethod
    def _regle_pour(entreprise_id, type_evenement):
        # Une règle spécifique entreprise prime sur une règle globale.
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
    def _traiter(cls, evenement, user=None):
        entreprise_id = evenement.entreprise_id or ""
        regle_mapping = cls._regle_pour(
            entreprise_id, evenement.type_evenement
        )
        if regle_mapping is None:
            evenement.statut = "IGNORE"
            evenement.erreur = ""
            evenement.processed_at = timezone.now()
            evenement.save(update_fields=["statut", "erreur", "processed_at"])
            return evenement

        try:
            with transaction.atomic():
                contexte = cls._contexte_regle(evenement.payload)
                # La configuration comptable est administrée côté moteur et
                # prime sur les valeurs métier pour les comptes/journaux.
                contexte.update(regle_mapping.configuration or {})

                resultats = moteur.appliquer(
                    regle_mapping.code_regle, **contexte
                )
                if not resultats:
                    evenement.statut = "IGNORE"
                    evenement.erreur = ""
                    evenement.processed_at = timezone.now()
                    evenement.save(
                        update_fields=["statut", "erreur", "processed_at"]
                    )
                    return evenement

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

                dimensions_globales = contexte.get("dimensions") or {}
                lignes = []
                for ligne in resultat.lignes:
                    lignes.append({
                        "compte": EcritureService.get_compte(
                            ligne.compte_code, entreprise_id
                        ),
                        "debit": ligne.debit,
                        "credit": ligne.credit,
                        "libelle": ligne.libelle or resultat.libelle,
                        "dimensions": ligne.dimensions or dimensions_globales,
                    })

                ecriture = EcritureService.creer_ecriture(
                    reference=resultat.reference,
                    date_ecriture=resultat.date_ecriture,
                    libelle=resultat.libelle,
                    journal=journal,
                    lignes=lignes,
                    user=user,
                    entreprise_id=entreprise_id,
                    source_system=evenement.source_system,
                    source_type=(
                        evenement.source_type
                        or evenement.type_evenement
                    ),
                    source_id=str(evenement.source_id or ""),
                    source_reference=str(
                        contexte.get("source_reference") or ""
                    ),
                    idempotency_key=evenement.idempotency_key,
                    metadata={
                        "event_type": evenement.type_evenement,
                        "event_id": evenement.pk,
                    },
                )

                evenement.ecriture = ecriture
                evenement.statut = "TRAITE"
                evenement.erreur = ""
                evenement.processed_at = timezone.now()
                evenement.save(
                    update_fields=[
                        "ecriture", "statut", "erreur", "processed_at"
                    ]
                )
            return evenement
        except Exception as exc:
            # L'inbox conserve l'échec alors que la transaction comptable
            # est rollbackée : audit et reprise restent possibles.
            evenement.statut = "ERREUR"
            evenement.erreur = str(exc)
            evenement.processed_at = timezone.now()
            evenement.save(
                update_fields=["statut", "erreur", "processed_at"]
            )
            return evenement

    @classmethod
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
                "payload": cls._payload_stockable(payload),
            },
        )
        if not created:
            return evenement, False

        return cls._traiter(evenement, user=user), True

    @classmethod
    def retraiter(cls, evenement, user=None):
        """Rejoue explicitement un événement IGNORE/ERREUR après correction."""
        if evenement.statut == "TRAITE":
            return evenement
        evenement.erreur = ""
        evenement.statut = "RECU"
        evenement.processed_at = None
        evenement.save(
            update_fields=["erreur", "statut", "processed_at"]
        )
        return cls._traiter(evenement, user=user)
