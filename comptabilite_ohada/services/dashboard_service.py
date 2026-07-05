from decimal import Decimal
from datetime import date, timedelta

from django.db.models import Sum, Q
from django.utils import timezone

from ..models import CompteComptable, EcritureComptable, LigneEcritureComptable
from ..models import ExerciceComptable


class DashboardService:
    """Agrégation des données pour le tableau de bord comptable."""

    @staticmethod
    def synthese(exercice=None):
        if exercice is None:
            exercice = ExerciceComptable.objects.filter(cloture=False).first()

        base = LigneEcritureComptable.objects.filter(ecriture__validee=True)
        if exercice:
            base = base.filter(
                ecriture__date_ecriture__gte=exercice.date_debut,
                ecriture__date_ecriture__lte=exercice.date_fin,
            )

        total_debit = base.aggregate(t=Sum("debit"))["t"] or Decimal("0.00")
        total_credit = base.aggregate(t=Sum("credit"))["t"] or Decimal("0.00")

        tresorerie = base.filter(
            Q(compte__code__startswith="57") |
            Q(compte__code__startswith="52") |
            Q(compte__code__startswith="581"),
        ).aggregate(
            debit=Sum("debit"), credit=Sum("credit"),
        )
        solde_tresorerie = (tresorerie["debit"] or Decimal("0.00")) - (tresorerie["credit"] or Decimal("0.00"))

        charges = base.filter(compte__code__startswith="6").aggregate(t=Sum("debit"))["t"] or Decimal("0.00")
        produits = base.filter(compte__code__startswith="7").aggregate(t=Sum("credit"))["t"] or Decimal("0.00")

        nb_ecritures = EcritureComptable.objects.filter(validee=True)
        if exercice:
            nb_ecritures = nb_ecritures.filter(exercice=exercice)

        return {
            "total_debit": total_debit,
            "total_credit": total_credit,
            "solde_tresorerie": solde_tresorerie,
            "total_charges": charges,
            "total_produits": produits,
            "resultat": produits - charges,
            "nb_ecritures": nb_ecritures.count(),
            "exercice": exercice,
        }

    @staticmethod
    def evolution_tresorerie(jours=30):
        depuis = timezone.now().date() - timedelta(days=jours)
        lignes = LigneEcritureComptable.objects.filter(
            ecriture__validee=True,
            ecriture__date_ecriture__gte=depuis,
        ).filter(
            Q(compte__code__startswith="57") |
            Q(compte__code__startswith="52") |
            Q(compte__code__startswith="581"),
        ).values("ecriture__date_ecriture").annotate(
            debit=Sum("debit"), credit=Sum("credit"),
        ).order_by("ecriture__date_ecriture")

        return [
            {
                "date": d["ecriture__date_ecriture"],
                "debit": d["debit"],
                "credit": d["credit"],
            }
            for d in lignes
        ]

    @staticmethod
    def alertes():
        alerts = []
        config = None
        try:
            from ..models import ConfigurationComptable
            config = ConfigurationComptable.get_config()
        except Exception:
            return alerts

        if config and not config.est_initialise:
            alerts.append({
                "niveau": "warning",
                "message": "Le plan comptable n'est pas encore initialisé",
            })

        nb_brouillon = EcritureComptable.objects.filter(validee=False).count()
        if nb_brouillon > 0:
            alerts.append({
                "niveau": "info",
                "message": f"{nb_brouillon} écriture(s) en brouillon à valider",
            })

        return alerts

    @staticmethod
    def compter_ecritures():
        return EcritureComptable.objects.count()

    @staticmethod
    def compter_ecritures_non_validees():
        return EcritureComptable.objects.filter(validee=False).count()

    @staticmethod
    def dernieres_ecritures(limit=10):
        return EcritureComptable.objects.select_related("journal", "exercice").order_by(
            "-date_ecriture", "-date_creation"
        )[:limit]

    @staticmethod
    def exercice_courant():
        exercice = ExerciceComptable.objects.filter(cloture=False).first()
        return str(exercice) if exercice else None

    @staticmethod
    def totaux_par_journal():
        from django.db.models import Sum
        return EcritureComptable.objects.values("journal__code").annotate(
            total=Sum("lignes__debit")
        ).order_by("journal__code")
