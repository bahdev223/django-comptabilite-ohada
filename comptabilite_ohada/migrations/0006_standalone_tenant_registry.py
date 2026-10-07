from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("comptabilite_ohada", "0005_external_events_analytics"),
    ]

    operations = [
        migrations.CreateModel(
            name="OrganisationComptable",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=100, unique=True)),
                ("nom", models.CharField(max_length=200)),
                ("actif", models.BooleanField(default=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Organisation comptable",
                "verbose_name_plural": "Organisations comptables",
                "ordering": ["nom"],
            },
        ),
        migrations.CreateModel(
            name="AccesEntrepriseComptable",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("ADMIN", "Administrateur"), ("COMPTABLE", "Comptable"), ("VALIDATEUR", "Validateur"), ("LECTURE", "Lecture seule")], default="LECTURE", max_length=20)),
                ("actif", models.BooleanField(default=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("entreprise", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="acces_utilisateurs", to="comptabilite_ohada.organisationcomptable")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="acces_comptables", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Accès entreprise comptable",
                "verbose_name_plural": "Accès entreprises comptables",
                "unique_together": {("user", "entreprise")},
            },
        ),
    ]
