from decimal import Decimal
from datetime import date

from django.db.models import Sum

from ..models import CompteComptable, LigneEcritureComptable, ExerciceComptable
from ..models import NatureCompte, CategorieCompte


class BilanService:
    """États financiers : Bilan, Compte de résultat."""

    CLASSE_BILAN_ACTIF = ["2"]
    CLASSE_BILAN_PASSIF = ["1"]
    CLASSE_CHARGES = ["6"]
    CLASSE_PRODUITS = ["7"]

    @staticmethod
    def bilan(exercice=None, date_arret=None):
        if date_arret is None:
            if exercice:
                date_arret = exercice.date_fin
            else:
                date_arret = date.today()

        lignes = LigneEcritureComptable.objects.filter(
            ecriture__validee=True,
            ecriture__date_ecriture__lte=date_arret,
        )
        if exercice:
            lignes = lignes.filter(ecriture__date_ecriture__gte=exercice.date_debut)

        actif = {}
        passif = {}

        for l in lignes.select_related("compte"):
            c = l.compte
            if c.categorie != CategorieCompte.BILAN.value:
                continue
            if c.code[0] in BilanService.CLASSE_BILAN_ACTIF:
                target = actif
            else:
                target = passif

            if c.code not in target:
                target[c.code] = {"compte": c, "debit": Decimal("0.00"), "credit": Decimal("0.00")}
            target[c.code]["debit"] += l.debit
            target[c.code]["credit"] += l.credit

        for d in (actif, passif):
            for v in d.values():
                v["solde"] = v["debit"] - v["credit"] if v["compte"].solde_normal == "DEBIT" \
                    else v["credit"] - v["debit"]

        total_actif = sum(v["solde"] for v in actif.values() if v["solde"] > 0)
        total_passif = sum(v["solde"] for v in passif.values() if v["solde"] > 0)

        return {
            "actif": [{"libelle": v["compte"].libelle, "montant": v["solde"]} for v in sorted(actif.values(), key=lambda x: x["compte"].code) if v["solde"] > 0],
            "passif": [{"libelle": v["compte"].libelle, "montant": v["solde"]} for v in sorted(passif.values(), key=lambda x: x["compte"].code) if v["solde"] > 0],
            "total_actif": total_actif,
            "total_passif": total_passif,
            "date_arret": date_arret,
        }

    @staticmethod
    def compte_resultat(exercice=None, date_debut=None, date_fin=None):
        if exercice:
            date_debut = exercice.date_debut
            date_fin = exercice.date_fin

        lignes = LigneEcritureComptable.objects.filter(
            ecriture__validee=True,
        )
        if date_debut:
            lignes = lignes.filter(ecriture__date_ecriture__gte=date_debut)
        if date_fin:
            lignes = lignes.filter(ecriture__date_ecriture__lte=date_fin)

        charges = {}
        produits = {}

        for l in lignes.select_related("compte"):
            c = l.compte
            if c.categorie != CategorieCompte.RESULTAT.value:
                continue
            if c.code[0] == "6":
                target = charges
            elif c.code[0] == "7":
                target = produits
            else:
                continue
            if c.code not in target:
                target[c.code] = {"compte": c, "debit": Decimal("0.00"), "credit": Decimal("0.00")}
            target[c.code]["debit"] += l.debit
            target[c.code]["credit"] += l.credit

        for d in (charges, produits):
            for v in d.values():
                v["solde"] = v["debit"] - v["credit"] if v["compte"].solde_normal == "DEBIT" \
                    else v["credit"] - v["debit"]

        total_charges = sum(v["solde"] for v in charges.values())
        total_produits = sum(v["solde"] for v in produits.values())
        resultat = total_produits - total_charges

        return {
            "charges": [{"libelle": v["compte"].libelle, "montant": v["solde"]} for v in sorted(charges.values(), key=lambda x: x["compte"].code)],
            "produits": [{"libelle": v["compte"].libelle, "montant": v["solde"]} for v in sorted(produits.values(), key=lambda x: x["compte"].code)],
            "total_charges": total_charges,
            "total_produits": total_produits,
            "resultat_net": resultat,
        }
