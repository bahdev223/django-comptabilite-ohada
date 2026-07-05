from .engine import RegleComptable, EcritureRegle, LigneRegle, moteur
from decimal import Decimal
from datetime import date


class RegleEncaissementClient(RegleComptable):
    """Encaissement client : Débit Caisse / Crédit Client (411)."""

    def __init__(self):
        super().__init__("ENCAISSEMENT_CLIENT", "Encaissement client")

    def appliquer(self, **contexte):
        montant = contexte.get("montant", 0)
        if montant <= 0:
            return None
        return EcritureRegle(
            reference=f"EN-{date.today().strftime('%Y%m%d%H%M%S')}",
            date_ecriture=date.today(),
            libelle=contexte.get("libelle", "Encaissement client"),
            journal_code="TR",
            lignes=[
                LigneRegle(compte_code=contexte.get("compte_caisse", "571"),
                           debit=Decimal(str(montant))),
                LigneRegle(compte_code=contexte.get("compte_client", "411"),
                           credit=Decimal(str(montant))),
            ],
        )


class ReglePaiementFournisseur(RegleComptable):
    """Paiement fournisseur : Débit Fournisseur (401) / Crédit Caisse."""

    def __init__(self):
        super().__init__("PAIEMENT_FOURNISSEUR", "Paiement fournisseur")

    def appliquer(self, **contexte):
        montant = contexte.get("montant", 0)
        if montant <= 0:
            return None
        return EcritureRegle(
            reference=f"PF-{date.today().strftime('%Y%m%d%H%M%S')}",
            date_ecriture=date.today(),
            libelle=contexte.get("libelle", "Paiement fournisseur"),
            journal_code="TR",
            lignes=[
                LigneRegle(compte_code=contexte.get("compte_fournisseur", "401"),
                           debit=Decimal(str(montant))),
                LigneRegle(compte_code=contexte.get("compte_caisse", "571"),
                           credit=Decimal(str(montant))),
            ],
        )


moteur.enregistrer(RegleEncaissementClient())
moteur.enregistrer(ReglePaiementFournisseur())
