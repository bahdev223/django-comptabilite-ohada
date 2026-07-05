from decimal import Decimal

from .engine import RegleComptable, EcritureRegle, LigneRegle, moteur
from ..services.ecriture_service import EcritureService


class RegleVenteAuComptant(RegleComptable):
    """Vente au comptant : Débit Caisse / Crédit Produit."""

    def __init__(self):
        super().__init__("VENTE_COMPTANT", "Vente au comptant")

    def appliquer(self, **contexte) -> EcritureRegle:
        montant = contexte.get("montant", 0)
        if montant <= 0:
            return None
        return EcritureRegle(
            reference=f"VN-{contexte.get('date', date.today()).strftime('%Y%m%d%H%M%S')}",
            date_ecriture=contexte.get("date", date.today()),
            libelle=contexte.get("libelle", "Vente au comptant"),
            journal_code="VN",
            lignes=[
                LigneRegle(compte_code=contexte.get("compte_caisse", "571"),
                           debit=Decimal(str(montant))),
                LigneRegle(compte_code=contexte.get("compte_produit", "701"),
                           credit=Decimal(str(montant))),
            ],
        )


class RegleAchatComptant(RegleComptable):
    """Achat au comptant : Débit Charge / Crédit Caisse."""

    def __init__(self):
        super().__init__("ACHAT_COMPTANT", "Achat au comptant")

    def appliquer(self, **contexte) -> EcritureRegle:
        montant = contexte.get("montant", 0)
        if montant <= 0:
            return None
        return EcritureRegle(
            reference=f"AC-{contexte.get('date', date.today()).strftime('%Y%m%d%H%M%S')}",
            date_ecriture=contexte.get("date", date.today()),
            libelle=contexte.get("libelle", "Achat au comptant"),
            journal_code="AC",
            lignes=[
                LigneRegle(compte_code=contexte.get("compte_charge", "601"),
                           debit=Decimal(str(montant))),
                LigneRegle(compte_code=contexte.get("compte_caisse", "571"),
                           credit=Decimal(str(montant))),
            ],
        )


from datetime import date
moteur.enregistrer(RegleVenteAuComptant())
moteur.enregistrer(RegleAchatComptant())
