from datetime import date, datetime
from decimal import Decimal

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
        if len(lignes_payload) < 2:
            raise ValidationError(
                "ECRITURE_GENERIQUE exige au moins deux lignes comptables."
            )

        date_operation = contexte.get("date") or date.today()
        if isinstance(date_operation, str):
            date_operation = parse_date(date_operation)
        if date_operation is None:
            raise ValidationError("Date d'opération invalide.")

        lignes = []
        for position, item in enumerate(lignes_payload, start=1):
            code = item.get("compte") or item.get("compte_code")
            if not code:
                raise ValidationError(
                    f"Ligne générique {position}: compte comptable obligatoire."
                )
            lignes.append(
                LigneRegle(
                    compte_code=str(code),
                    debit=Decimal(str(item.get("debit", 0) or 0)),
                    credit=Decimal(str(item.get("credit", 0) or 0)),
                    libelle=item.get("libelle"),
                    dimensions=item.get("dimensions") or {},
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


moteur.enregistrer(RegleEcritureGenerique())
