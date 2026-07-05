"""
Constantes SYSCOHADA révisées.

Classes, types de comptes, natures, journaux selon le plan comptable OHADA.
"""

CLASSES_COMPTABLES = {
    1: "Comptes de ressources durables",
    2: "Comptes de l'actif immobilisé",
    3: "Comptes de stocks",
    4: "Comptes de tiers",
    5: "Comptes de trésorerie",
    6: "Comptes de charges",
    7: "Comptes de produits",
    8: "Comptes des engagements hors bilan",
}

NATURES_COMPTE = [
    ("DEBIT", "Débiteur"),
    ("CREDIT", "Créditeur"),
    ("DEBIT_CREDIT", "Débiteur ou Créditeur"),
]

TYPES_COMPTE = [
    ("BILAN", "Bilan"),
    ("GESTION", "Gestion"),
    ("HORS_BILAN", "Hors bilan"),
    ("ORDRE", "Ordre"),
]

CATEGORIES_COMPTE = [
    ("TRESORERIE", "Trésorerie"),
    ("BANQUE", "Banque"),
    ("CAISSE", "Caisse"),
    ("CLIENT", "Client"),
    ("FOURNISSEUR", "Fournisseur"),
    ("PERSONNEL", "Personnel"),
    ("ETAT", "État"),
    ("STOCK", "Stock"),
    ("IMMOBILISATION", "Immobilisation"),
    ("AMORTISSEMENT", "Amortissement"),
    ("CAPITAL", "Capital"),
    ("RESULTAT", "Résultat"),
    ("CHARGE", "Charge"),
    ("PRODUIT", "Produit"),
    ("AUTRE", "Autre"),
]

TYPES_JOURNAL = [
    ("VN", "Journal des ventes"),
    ("AC", "Journal des achats"),
    ("TR", "Journal de trésorerie"),
    ("OD", "Journal des opérations diverses"),
    ("BQ", "Journal de banque"),
    ("CP", "Journal de caisse"),
    ("AN", "Journal des à-nouveaux"),
    ("SA", "Journal des salaires"),
    ("IN", "Journal des immobilisations"),
    ("ST", "Journal des stocks"),
]

MODES_AMORTISSEMENT = [
    ("LINEAIRE", "Linéaire"),
    ("DEGRESSIF", "Dégressif"),
    ("PROGRESSIF", "Progressif"),
]

STATUTS_IMMOBILISATION = [
    ("ACTIF", "Actif"),
    ("CESSION", "Cédé"),
    ("MISE_AU_REBUT", "Mise au rebut"),
    ("EN_CONSTRUCTION", "En construction"),
]

STATUTS_ECRITURE = [
    ("BROUILLON", "Brouillon"),
    ("VALIDEE", "Validée"),
    ("ANNULEE", "Annulée"),
]

SENS_LIGNE = [
    ("DEBIT", "Débit"),
    ("CREDIT", "Crédit"),
]

TYPES_OPERATION = [
    ("VENTE", "Vente"),
    ("ACHAT", "Achat"),
    ("CHARGE", "Charge"),
    ("PRODUIT", "Produit"),
    ("TRESORERIE", "Trésorerie"),
    ("IMMOBILISATION", "Immobilisation"),
    ("STOCK", "Stock"),
    ("SALAIRE", "Salaire"),
    ("REGULARISATION", "Régularisation"),
    ("OUVERTURE", "Ouverture"),
    ("CLOTURE", "Clôture"),
]
