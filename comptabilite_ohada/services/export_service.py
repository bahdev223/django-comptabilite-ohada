from decimal import Decimal
from io import BytesIO
from datetime import date

from django.http import HttpResponse
from django.db.models import Sum

from ..models import CompteComptable, EcritureComptable, LigneEcritureComptable
from ..models import ExerciceComptable, JournalComptable
from .journal_service import BalanceService


class ExportService:
    """Export des états comptables (CSV, Excel, PDF)."""

    @staticmethod
    def export_balance_csv(exercice=None):
        import csv
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = "attachment; filename=balance.csv"
        writer = csv.writer(response)
        writer.writerow(["Code", "Compte", "Débit", "Crédit", "Solde"])
        for ligne in BalanceService.balance(exercice):
            c = ligne["compte"]
            writer.writerow([
                c.code,
                c.libelle,
                f"{ligne['total_debit']:.2f}",
                f"{ligne['total_credit']:.2f}",
                f"{ligne['solde']:.2f}",
            ])
        return response

    @staticmethod
    def export_grand_livre_csv(compte_code=None, exercice=None):
        import csv
        from .journal_service import GrandLivreService
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = "attachment; filename=grand_livre.csv"
        writer = csv.writer(response)
        writer.writerow(["Date", "Référence", "Libellé", "Compte", "Débit", "Crédit"])
        for l in GrandLivreService.grand_livre(compte_code, exercice):
            c = l["compte"]
            writer.writerow([
                l["date"], l["reference"], l["libelle"],
                f"{c.code} - {c.libelle}",
                f"{l['debit']:.2f}", f"{l['credit']:.2f}",
            ])
        return response

    @staticmethod
    def export_bilan_csv(exercice=None):
        import csv
        from .bilan_service import BilanService
        bilan = BilanService.bilan(exercice)
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = "attachment; filename=bilan.csv"
        writer = csv.writer(response)
        writer.writerow(["BILAN", "", "", "", ""])
        writer.writerow(["ACTIF", "Solde", "", "PASSIF", "Solde"])
        max_len = max(len(bilan["actif"]), len(bilan["passif"]))
        for i in range(max_len):
            act = bilan["actif"][i] if i < len(bilan["actif"]) else None
            pas = bilan["passif"][i] if i < len(bilan["passif"]) else None
            writer.writerow([
                f"{act['libelle']}" if act else "",
                f"{act['montant']:.2f}" if act else "",
                "",
                f"{pas['libelle']}" if pas else "",
                f"{pas['montant']:.2f}" if pas else "",
            ])
        writer.writerow([])
        writer.writerow(["Total Actif", f"{bilan['total_actif']:.2f}",
                        "", "Total Passif", f"{bilan['total_passif']:.2f}"])
        return response

    @staticmethod
    def export_ecritures_csv(exercice=None):
        import csv
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = "attachment; filename=ecritures.csv"
        writer = csv.writer(response)
        writer.writerow(["Date", "Référence", "Journal", "Libellé", "Compte", "Débit", "Crédit", "Validée"])
        qs = EcritureComptable.objects.select_related("journal").prefetch_related("lignes__compte")
        if exercice:
            qs = qs.filter(exercice=exercice)
        for e in qs.order_by("date_ecriture"):
            for l in e.lignes.all():
                writer.writerow([
                    e.date_ecriture, e.reference, e.journal.code,
                    e.libelle[:80], f"{l.compte.code} - {l.compte.libelle}",
                    f"{l.debit:.2f}", f"{l.credit:.2f}",
                    "Oui" if e.validee else "Non",
                ])
        return response
