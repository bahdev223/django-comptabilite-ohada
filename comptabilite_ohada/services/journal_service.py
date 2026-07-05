from decimal import Decimal
from datetime import date, timedelta

from django.db.models import Sum, Q
from django.utils import timezone

from ..models import EcritureComptable, LigneEcritureComptable, CompteComptable
from ..models import JournalComptable, ExerciceComptable


class JournalService:
    """Gestion des journaux comptables."""

    @staticmethod
    def total_journal(journal, date_debut=None, date_fin=None):
        qs = EcritureComptable.objects.filter(journal=journal, validee=True)
        if date_debut:
            qs = qs.filter(date_ecriture__gte=date_debut)
        if date_fin:
            qs = qs.filter(date_ecriture__lte=date_fin)
        ecritures = qs.values_list("id", flat=True)
        lignes = LigneEcritureComptable.objects.filter(ecriture_id__in=ecritures)
        return {
            "total_debit": lignes.aggregate(total=Sum("debit"))["total"] or Decimal("0.00"),
            "total_credit": lignes.aggregate(total=Sum("credit"))["total"] or Decimal("0.00"),
            "nb_ecritures": qs.count(),
        }

    @staticmethod
    def liste_avec_totaux(exercice=None):
        journaux = JournalComptable.objects.filter(actif=True)
        result = []
        for j in journaux:
            qs = EcritureComptable.objects.filter(journal=j, validee=True)
            if exercice:
                qs = qs.filter(exercice=exercice)
            lignes = LigneEcritureComptable.objects.filter(ecriture_id__in=qs.values("id"))
            result.append({
                "journal": j,
                "nb_ecritures": qs.count(),
                "total_debit": lignes.aggregate(t=Sum("debit"))["t"] or Decimal("0.00"),
                "total_credit": lignes.aggregate(t=Sum("credit"))["t"] or Decimal("0.00"),
            })
        return result


class BalanceService:
    """Balance des comptes."""

    @staticmethod
    def balance(exercice=None, date_debut=None, date_fin=None):
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

        data = {}
        for l in lignes.select_related("compte").order_by("compte__code"):
            c = l.compte
            if c.code not in data:
                data[c.code] = {
                    "compte": c,
                    "total_debit": Decimal("0.00"),
                    "total_credit": Decimal("0.00"),
                }
            data[c.code]["total_debit"] += l.debit
            data[c.code]["total_credit"] += l.credit

        for v in data.values():
            solde_normal = v["compte"].solde_normal
            if solde_normal == "DEBIT":
                v["solde"] = v["total_debit"] - v["total_credit"]
            else:
                v["solde"] = v["total_credit"] - v["total_debit"]

        return sorted(data.values(), key=lambda x: x["compte"].code)

    @staticmethod
    def solde_compte(compte, exercice=None):
        lignes = LigneEcritureComptable.objects.filter(
            compte=compte, ecriture__validee=True,
        )
        if exercice:
            lignes = lignes.filter(
                ecriture__date_ecriture__gte=exercice.date_debut,
                ecriture__date_ecriture__lte=exercice.date_fin,
            )
        debit = lignes.aggregate(t=Sum("debit"))["t"] or Decimal("0.00")
        credit = lignes.aggregate(t=Sum("credit"))["t"] or Decimal("0.00")
        if compte.solde_normal == "DEBIT":
            return debit - credit
        return credit - debit


class GrandLivreService:
    """Grand livre des comptes."""

    @staticmethod
    def grand_livre(compte_code=None, exercice=None, date_debut=None, date_fin=None):
        lignes = LigneEcritureComptable.objects.filter(
            ecriture__validee=True,
        ).select_related("ecriture", "compte").order_by("ecriture__date_ecriture")

        if compte_code:
            lignes = lignes.filter(compte__code__startswith=compte_code)
        if exercice:
            lignes = lignes.filter(
                ecriture__date_ecriture__gte=exercice.date_debut,
                ecriture__date_ecriture__lte=exercice.date_fin,
            )
        if date_debut:
            lignes = lignes.filter(ecriture__date_ecriture__gte=date_debut)
        if date_fin:
            lignes = lignes.filter(ecriture__date_ecriture__lte=date_fin)

        return [
            {
                "date": l.ecriture.date_ecriture,
                "reference": l.ecriture.reference,
                "libelle": l.libelle or l.ecriture.libelle,
                "compte": l.compte,
                "debit": l.debit,
                "credit": l.credit,
            }
            for l in lignes
        ]
