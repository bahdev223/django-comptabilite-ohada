"""
Moteur de règles comptables.

Chaque règle définit quelles écritures générer pour un type d'opération métier.
Les règles sont appelées par les intégrations lorsqu'un signal est reçu.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Callable
from decimal import Decimal
from datetime import date


@dataclass
class LigneRegle:
    compte_code: str
    debit: Decimal = Decimal("0.00")
    credit: Decimal = Decimal("0.00")
    libelle: Optional[str] = None


@dataclass
class EcritureRegle:
    reference: str
    date_ecriture: date
    libelle: str
    journal_code: str
    lignes: List[LigneRegle] = field(default_factory=list)


class RegleComptable:
    """Une règle comptable = une fonction qui produit des écritures."""

    def __init__(self, code: str, libelle: str, description: str = ""):
        self.code = code
        self.libelle = libelle
        self.description = description

    def appliquer(self, **contexte) -> Optional[EcritureRegle]:
        """Applique la règle avec le contexte donné.
        Retourne une EcritureRegle ou None si la règle ne s'applique pas.
        """
        raise NotImplementedError


class MoteurRegles:
    """Moteur d'application des règles comptables."""

    def __init__(self):
        self._regles: List[RegleComptable] = []

    def enregistrer(self, regle: RegleComptable):
        self._regles.append(regle)

    def appliquer(self, type_operation: str, **contexte) -> List[EcritureRegle]:
        """Applique toutes les règles compatibles."""
        resultats = []
        for regle in self._regles:
            try:
                ecriture = regle.appliquer(**contexte)
                if ecriture:
                    resultats.append(ecriture)
            except Exception:
                continue
        return resultats


# Instance globale du moteur
moteur = MoteurRegles()
