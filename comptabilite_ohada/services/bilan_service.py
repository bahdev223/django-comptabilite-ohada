from decimal import Decimal
from datetime import date

from ..models import LigneEcritureComptable
from ..models import NatureCompte, CategorieCompte


class BilanService:
    """États de synthèse issus exclusivement des écritures validées."""

    CHARGES_HAO = {"81", "83", "85", "87", "89"}
    PRODUITS_HAO = {"82", "84", "86", "88"}

    @staticmethod
    def _lignes_valides(entreprise_id="", exercice=None):
        qs = LigneEcritureComptable.objects.filter(
            ecriture__validee=True,
            ecriture__entreprise_id=entreprise_id or "",
        ).exclude(
            ecriture__source_type="fiscal_closure",
        ).exclude(
            ecriture__reversal_of__source_type="fiscal_closure",
        )
        if exercice:
            qs = qs.filter(
                ecriture__date_ecriture__gte=exercice.date_debut,
                ecriture__date_ecriture__lte=exercice.date_fin,
            )
        return qs

    @staticmethod
    def bilan(exercice=None, date_arret=None, entreprise_id=""):
        if exercice:
            entreprise_id = exercice.entreprise_id or ""
            if date_arret is None:
                date_arret = exercice.date_fin
        elif date_arret is None:
            date_arret = date.today()

        lignes = LigneEcritureComptable.objects.filter(
            ecriture__validee=True,
            ecriture__entreprise_id=entreprise_id or "",
            ecriture__date_ecriture__lte=date_arret,
        )
        if exercice:
            lignes = lignes.filter(
                ecriture__date_ecriture__gte=exercice.date_debut
            )

        data = {}
        for ligne in lignes.select_related("compte"):
            compte = ligne.compte
            if compte.categorie != CategorieCompte.BILAN.value:
                continue
            item = data.setdefault(
                compte.code,
                {
                    "compte": compte,
                    "debit": Decimal("0.00"),
                    "credit": Decimal("0.00"),
                },
            )
            item["debit"] += ligne.debit
            item["credit"] += ligne.credit

        actif = []
        passif = []

        for item in data.values():
            compte = item["compte"]
            debit_net = item["debit"] - item["credit"]

            # Ressources durables : toujours présentées au passif, une perte
            # ou un compte débiteur venant diminuer le passif.
            if compte.code.startswith("1"):
                montant = -debit_net
                if montant:
                    passif.append({"compte": compte, "montant": montant})
                continue

            # Immobilisations/stocks : restent à l'actif. Les comptes de sens
            # créditeur (amortissements/dépréciations) réduisent l'actif.
            if compte.code.startswith(("2", "3")):
                montant = debit_net
                if montant:
                    actif.append({"compte": compte, "montant": montant})
                continue

            if compte.nature == NatureCompte.ACTIF:
                montant = debit_net
                if montant >= 0:
                    actif.append({"compte": compte, "montant": montant})
                else:
                    passif.append({"compte": compte, "montant": -montant})
            elif compte.nature == NatureCompte.PASSIF:
                montant = -debit_net
                if montant >= 0:
                    passif.append({"compte": compte, "montant": montant})
                else:
                    actif.append({"compte": compte, "montant": -montant})
            else:
                # Comptes mixtes de tiers/trésorerie : classement selon le
                # solde réellement débiteur ou créditeur.
                if debit_net > 0:
                    actif.append({"compte": compte, "montant": debit_net})
                elif debit_net < 0:
                    passif.append({"compte": compte, "montant": -debit_net})

        actif.sort(key=lambda x: x["compte"].code)
        passif.sort(key=lambda x: x["compte"].code)

        resultat_courant = None
        if exercice:
            from ..models import EcritureComptable

            clotures = EcritureComptable.objects.filter(
                exercice=exercice,
                validee=True,
                source_type="fiscal_closure",
                source_id=str(exercice.pk),
            )
            cloture_active = any(
                not ecriture.reversals.filter(validee=True).exists()
                for ecriture in clotures
            )
            if not cloture_active:
                resultat_courant = BilanService.compte_resultat(
                    exercice=exercice,
                    entreprise_id=entreprise_id,
                )["resultat_net"]

        total_actif = sum((x["montant"] for x in actif), Decimal("0.00"))
        total_passif = sum((x["montant"] for x in passif), Decimal("0.00"))
        if resultat_courant is not None:
            total_passif += resultat_courant

        return {
            "actif": [
                {
                    "code": x["compte"].code,
                    "libelle": x["compte"].libelle,
                    "montant": x["montant"],
                }
                for x in actif
            ],
            "passif": [
                {
                    "code": x["compte"].code,
                    "libelle": x["compte"].libelle,
                    "montant": x["montant"],
                }
                for x in passif
            ] + (
                [{
                    "code": "RESULTAT_COURANT",
                    "libelle": "Résultat courant de l'exercice",
                    "montant": resultat_courant,
                }]
                if resultat_courant is not None and resultat_courant != 0
                else []
            ),
            "total_actif": total_actif,
            "total_passif": total_passif,
            "ecart": total_actif - total_passif,
            "date_arret": date_arret,
        }

    @classmethod
    def compte_resultat(
        cls, exercice=None, date_debut=None, date_fin=None, entreprise_id=""
    ):
        if exercice:
            date_debut = exercice.date_debut
            date_fin = exercice.date_fin
            entreprise_id = exercice.entreprise_id or ""

        lignes = cls._lignes_valides(
            entreprise_id=entreprise_id,
            exercice=None,
        )
        if date_debut:
            lignes = lignes.filter(ecriture__date_ecriture__gte=date_debut)
        if date_fin:
            lignes = lignes.filter(ecriture__date_ecriture__lte=date_fin)

        charges = {}
        produits = {}

        for ligne in lignes.select_related("compte"):
            compte = ligne.compte
            if compte.categorie != CategorieCompte.RESULTAT.value:
                continue

            prefix = compte.code[:2]
            if compte.code.startswith("6") or prefix in cls.CHARGES_HAO:
                target = charges
                sens = "charge"
            elif compte.code.startswith("7") or prefix in cls.PRODUITS_HAO:
                target = produits
                sens = "produit"
            else:
                continue

            item = target.setdefault(
                compte.code,
                {
                    "compte": compte,
                    "debit": Decimal("0.00"),
                    "credit": Decimal("0.00"),
                    "sens": sens,
                },
            )
            item["debit"] += ligne.debit
            item["credit"] += ligne.credit

        for item in charges.values():
            item["solde"] = item["debit"] - item["credit"]
        for item in produits.values():
            item["solde"] = item["credit"] - item["debit"]

        total_charges = sum(
            (x["solde"] for x in charges.values()), Decimal("0.00")
        )
        total_produits = sum(
            (x["solde"] for x in produits.values()), Decimal("0.00")
        )

        return {
            "charges": [
                {
                    "code": x["compte"].code,
                    "libelle": x["compte"].libelle,
                    "montant": x["solde"],
                }
                for x in sorted(charges.values(), key=lambda x: x["compte"].code)
                if x["solde"]
            ],
            "produits": [
                {
                    "code": x["compte"].code,
                    "libelle": x["compte"].libelle,
                    "montant": x["solde"],
                }
                for x in sorted(produits.values(), key=lambda x: x["compte"].code)
                if x["solde"]
            ],
            "total_charges": total_charges,
            "total_produits": total_produits,
            "resultat_net": total_produits - total_charges,
        }
