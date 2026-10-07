from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import json

from django.core.exceptions import ValidationError
from django.utils.dateparse import parse_date

from .engine import RegleComptable, EcritureRegle, LigneRegle, moteur


class RegleEcritureGenerique(RegleComptable):
    """Règle de secours pour une plateforme qui fournit déjà le mapping comptable.

    Elle reste abstraite : aucun concept BTP/Solar/Projet n'est connu ici.
    """

    def __init__(self):
        super().__init__(
            "ECRITURE_GENERIQUE",
            "Écriture générique",
            "Construit une écriture à partir de lignes comptables explicites.",
        )

    def appliquer(self, **contexte):
        lignes_payload = contexte.get("lignes") or []
        if not isinstance(lignes_payload, list) or len(lignes_payload) < 2:
            raise ValidationError(
                "ECRITURE_GENERIQUE exige au moins deux lignes comptables."
            )

        date_operation = contexte.get("date")
        if isinstance(date_operation, str):
            date_operation = parse_date(date_operation)
        if not isinstance(date_operation, date):
            raise ValidationError("Date d'opération invalide.")

        dimensions_globales = self._dimensions(contexte.get("dimensions", {}))
        lignes = []
        for position, item in enumerate(lignes_payload, start=1):
            if not isinstance(item, dict):
                raise ValidationError(f"Ligne générique {position}: objet obligatoire.")
            code = item.get("compte") or item.get("compte_code")
            if not isinstance(code, str) or not code.strip():
                raise ValidationError(
                    f"Ligne générique {position}: compte comptable obligatoire."
                )
            dimensions = self._dimensions(item.get("dimensions", {}))
            if any(
                axis in dimensions_globales and json.dumps(dimensions_globales[axis], sort_keys=True) != json.dumps(value, sort_keys=True)
                for axis, value in dimensions.items()
            ):
                raise ValidationError("La ligne contredit les dimensions communes de l'événement.")
            lignes.append(
                LigneRegle(
                    compte_code=code.strip(),
                    debit=self._montant(item.get("debit", 0)),
                    credit=self._montant(item.get("credit", 0)),
                    libelle=item.get("libelle"),
                    dimensions={**dimensions_globales, **dimensions},
                )
            )

        return EcritureRegle(
            reference=contexte.get("reference")
            or f"EVT-{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
            date_ecriture=date_operation,
            libelle=contexte.get("libelle", "Écriture issue d'un événement métier"),
            journal_code=contexte.get("journal_code", "OD"),
            lignes=lignes,
        )

    @staticmethod
    def _montant(value):
        try:
            montant = Decimal(str(value))
            if (
                isinstance(value, bool) or not montant.is_finite()
                or montant < 0 or montant >= Decimal("10000000000000")
                or montant != montant.quantize(Decimal("0.01"))
            ):
                raise ValueError
            return montant
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValidationError("Montant comptable invalide.") from exc

    @staticmethod
    def _dimensions(value):
        if not isinstance(value, dict):
            raise ValidationError("Les dimensions doivent être un objet.")
        # Les valeurs riches et les ventilations de #1 restent acceptées.
        dimensions = {}
        for axis, item in value.items():
            if not isinstance(axis, str) or not axis.strip() or len(axis) > 50:
                raise ValidationError("Code de dimension analytique invalide.")
            code = axis.upper()
            if code in dimensions:
                raise ValidationError("Deux axes désignent la même dimension analytique.")
            dimensions[code] = item
        return dimensions


moteur.enregistrer(RegleEcritureGenerique())
