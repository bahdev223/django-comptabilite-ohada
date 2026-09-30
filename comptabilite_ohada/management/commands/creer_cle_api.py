from django.core.management.base import BaseCommand, CommandError

from comptabilite_ohada.models import (
    ApplicationClienteComptable,
    OrganisationComptable,
)


class Command(BaseCommand):
    help = "Crée une clé API machine-to-machine pour une organisation comptable."

    def add_arguments(self, parser):
        parser.add_argument("--entreprise", required=True)
        parser.add_argument("--nom", required=True)
        parser.add_argument(
            "--scope",
            action="append",
            dest="scopes",
            default=[],
            help=(
                "Scope autorisé. Répéter l'option. Exemples: "
                "accounting.read, accounting.events.write, accounting.write, "
                "accounting.validate ou *"
            ),
        )

    def handle(self, *args, **options):
        entreprise = OrganisationComptable.objects.filter(
            code=options["entreprise"],
            actif=True,
        ).first()
        if entreprise is None:
            raise CommandError("Organisation comptable introuvable ou inactive.")

        if ApplicationClienteComptable.objects.filter(
            entreprise=entreprise,
            nom=options["nom"],
        ).exists():
            raise CommandError(
                "Une application de ce nom existe déjà. Révoquez-la ou utilisez un autre nom."
            )

        application, secret = ApplicationClienteComptable.generer_cle(
            entreprise=entreprise,
            nom=options["nom"],
            scopes=options["scopes"],
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Clé créée pour {application}. Copiez-la maintenant :"
            )
        )
        self.stdout.write(secret)
        self.stdout.write(
            "Le secret brut n'est pas stocké et ne pourra pas être relu."
        )
