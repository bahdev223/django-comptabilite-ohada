import django.db.models.deletion
from django.db import migrations, models
from django.db.models import F, Q


class Migration(migrations.Migration):

    dependencies = [
        ("comptabilite_ohada", "0009_mobile_money_default"),
    ]

    operations = [
        migrations.AddField(
            model_name="soldeinitialcomptable",
            name="mobile_money",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=15),
        ),
        migrations.AddConstraint(
            model_name="configurationcomptable",
            constraint=models.UniqueConstraint(
                fields=("entreprise_id",),
                name="uniq_configuration_comptable_par_entreprise",
            ),
        ),
        migrations.AddConstraint(
            model_name="exercicecomptable",
            constraint=models.CheckConstraint(
                condition=Q(date_fin__gte=F("date_debut")),
                name="exercice_dates_valides",
            ),
        ),
        migrations.AlterField(
            model_name="ecriturecomptable",
            name="journal",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="ecritures",
                to="comptabilite_ohada.journalcomptable",
                verbose_name="Journal",
            ),
        ),
        migrations.AlterField(
            model_name="ecriturecomptable",
            name="exercice",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="ecritures",
                to="comptabilite_ohada.exercicecomptable",
                verbose_name="Exercice",
            ),
        ),
        migrations.CreateModel(
            name="ApplicationClienteComptable",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nom", models.CharField(max_length=150)),
                ("prefixe", models.CharField(db_index=True, max_length=16, unique=True)),
                ("secret_hash", models.CharField(max_length=64)),
                ("scopes", models.JSONField(blank=True, default=list)),
                ("actif", models.BooleanField(default=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("entreprise", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="applications_clientes", to="comptabilite_ohada.organisationcomptable")),
            ],
            options={
                "verbose_name": "Application cliente comptable",
                "verbose_name_plural": "Applications clientes comptables",
                "ordering": ["entreprise__code", "nom"],
                "unique_together": {("entreprise", "nom")},
            },
        ),
    ]
