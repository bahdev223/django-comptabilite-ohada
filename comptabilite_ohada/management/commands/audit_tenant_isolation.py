"""Read-only audit of tenant anomalies after applying migrations on a restored DB."""
import json

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, F

from comptabilite_ohada.models import (
    CompteComptable, JournalComptable, ExerciceComptable,
    EcritureComptable, LigneEcritureComptable, ConfigurationComptable,
    Immobilisation, ReleveBancaire,
)


class Command(BaseCommand):
    help = (
        "Read-only tenant audit: legacy unassigned rows, cross-tenant FKs and "
        "duplicate configurations. Run on a restored copy before deployment."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--fail-on-anomaly", action="store_true",
            help="Exit with failure if any legacy or cross-tenant records remain.",
        )

    def handle(self, *args, **options):
        models = (
            CompteComptable, JournalComptable, ExerciceComptable,
            EcritureComptable, ConfigurationComptable, Immobilisation,
            ReleveBancaire,
        )
        unassigned = {
            model._meta.model_name: model.objects.filter(entreprise_id="").count()
            for model in models
        }
        cross_tenant = {
            "ecriture_journal": EcritureComptable.objects.exclude(
                journal__entreprise_id=F("entreprise_id")
            ).count(),
            "ecriture_exercice": EcritureComptable.objects.exclude(
                exercice__entreprise_id=F("entreprise_id")
            ).count(),
            "ecriture_ligne_compte": LigneEcritureComptable.objects.exclude(
                ecriture__entreprise_id=F("compte__entreprise_id")
            ).count(),
            "compte_parent": CompteComptable.objects.filter(
                parent__isnull=False,
            ).exclude(parent__entreprise_id=F("entreprise_id")).count(),
        }
        duplicate_configs = (
            ConfigurationComptable.objects.exclude(entreprise_id="")
            .values("entreprise_id")
            .annotate(n=Count("id"))
            .filter(n__gt=1)
            .count()
        )
        result = {
            "unassigned": unassigned,
            "cross_tenant": cross_tenant,
            "duplicate_config_companies": duplicate_configs,
        }
        self.stdout.write(json.dumps(result, sort_keys=True))
        anomalies = sum(unassigned.values()) + sum(cross_tenant.values()) + duplicate_configs
        if anomalies and options["fail_on_anomaly"]:
            raise CommandError(
                f"{anomalies} anomalie(s) de cloisonnement : "
                "réattribution auditée requise, aucune correction automatique."
            )
