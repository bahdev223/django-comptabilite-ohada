import json
import os
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from comptabilite_ohada.services.initialisation_service import InitialisationService


class Command(BaseCommand):
    help = "Charge le plan comptable SYSCOHADA à partir d'un fichier JSON"

    def add_arguments(self, parser):
        parser.add_argument(
            "--fichier",
            type=str,
            default=None,
            help="Chemin vers le fichier JSON du plan comptable",
        )
        parser.add_argument(
            "--societe",
            type=str,
            default=None,
            help="Identifiant de la société (optionnel)",
        )
        parser.add_argument(
            "--ecraser",
            action="store_true",
            default=False,
            help="Écraser les comptes existants",
        )

    def handle(self, *args, **options):
        fichier = options.get("fichier")
        if not fichier:
            fichier = os.path.join(
                settings.BASE_DIR, "comptabilite_ohada", "data", "plan_comptable.json"
            )
            if not os.path.exists(fichier):
                fichier = os.path.join(
                    os.path.dirname(__file__), "..", "..", "data", "plan_comptable.json"
                )

        if not os.path.exists(fichier):
            raise CommandError(f"Fichier introuvable : {fichier}")

        with open(fichier, "r", encoding="utf-8") as f:
            donnees = json.load(f)

        service = InitialisationService()
        comptes = service.charger_plan_comptable(
            donnees, societe=options.get("societe"), ecraser=options.get("ecraser")
        )

        self.stdout.write(
            self.style.SUCCESS(f"{len(comptes)} comptes chargés avec succès depuis {fichier}")
        )
