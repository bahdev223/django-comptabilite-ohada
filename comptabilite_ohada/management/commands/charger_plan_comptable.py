from django.core.management.base import BaseCommand, CommandError

from comptabilite_ohada.services.initialisation_service import InitialisationService


class Command(BaseCommand):
    help = "Charge le plan comptable SYSCOHADA fourni avec le paquet."

    def add_arguments(self, parser):
        parser.add_argument(
            "--ecraser",
            action="store_true",
            default=False,
            help="Écraser les comptes existants.",
        )

    def handle(self, *args, **options):
        resultat = InitialisationService.charger_plan_comptable(
            force=options["ecraser"]
        )
        if not resultat.get("success"):
            raise CommandError(resultat.get("error", "Initialisation impossible"))
        self.stdout.write(
            self.style.SUCCESS(
                f"{resultat['total']} comptes disponibles "
                f"({resultat['comptes_crees']} créés)."
            )
        )
