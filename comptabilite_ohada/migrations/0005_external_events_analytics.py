# Generated for autonomous accounting API and analytics architecture.

import django.db.models.deletion
from django.db import migrations, models
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ("comptabilite_ohada", "0004_tenant_scope_configuration_assets_bank"),
    ]

    operations = [
        migrations.AddField(
            model_name="ecriturecomptable",
            name="validated_by",
            field=models.CharField(blank=True, max_length=100, null=True, verbose_name="Validé par"),
        ),
        migrations.AddField(
            model_name="ecriturecomptable",
            name="source_system",
            field=models.CharField(blank=True, db_index=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="ecriturecomptable",
            name="source_type",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="ecriturecomptable",
            name="source_id",
            field=models.CharField(blank=True, db_index=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="ecriturecomptable",
            name="source_reference",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="ecriturecomptable",
            name="idempotency_key",
            field=models.CharField(blank=True, db_index=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="ecriturecomptable",
            name="metadata",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="ecriturecomptable",
            name="reversal_of",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="reversals", to="comptabilite_ohada.ecriturecomptable",
                verbose_name="Contre-passation de",
            ),
        ),
        migrations.CreateModel(
            name="DimensionAnalytique",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("entreprise_id", models.CharField(blank=True, db_index=True, default="", max_length=255)),
                ("code", models.CharField(max_length=50)),
                ("libelle", models.CharField(max_length=150)),
                ("actif", models.BooleanField(default=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
            ],
            options={
                "verbose_name": "Dimension analytique",
                "verbose_name_plural": "Dimensions analytiques",
                "ordering": ["code"],
                "unique_together": {("entreprise_id", "code")},
            },
        ),
        migrations.CreateModel(
            name="ValeurAnalytique",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=100)),
                ("libelle", models.CharField(max_length=200)),
                ("external_id", models.CharField(blank=True, db_index=True, default="", max_length=255)),
                ("actif", models.BooleanField(default=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("dimension", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="valeurs", to="comptabilite_ohada.dimensionanalytique")),
            ],
            options={
                "verbose_name": "Valeur analytique",
                "verbose_name_plural": "Valeurs analytiques",
                "ordering": ["dimension__code", "code"],
                "unique_together": {("dimension", "code")},
            },
        ),
        migrations.CreateModel(
            name="AffectationAnalytique",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("pourcentage", models.DecimalField(decimal_places=2, default=Decimal("100.00"), max_digits=5)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("dimension", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="affectations", to="comptabilite_ohada.dimensionanalytique")),
                ("ligne", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="affectations_analytiques", to="comptabilite_ohada.ligneecriturecomptable")),
                ("valeur", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="affectations", to="comptabilite_ohada.valeuranalytique")),
            ],
            options={
                "verbose_name": "Affectation analytique",
                "verbose_name_plural": "Affectations analytiques",
                "unique_together": {("ligne", "dimension")},
            },
        ),
        migrations.CreateModel(
            name="RegleEvenementComptable",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("entreprise_id", models.CharField(blank=True, db_index=True, default="", max_length=255)),
                ("type_evenement", models.CharField(max_length=100)),
                ("code_regle", models.CharField(max_length=100)),
                ("actif", models.BooleanField(default=True)),
                ("configuration", models.JSONField(blank=True, default=dict)),
            ],
            options={
                "verbose_name": "Règle d'événement comptable",
                "verbose_name_plural": "Règles d'événements comptables",
                "ordering": ["type_evenement"],
                "unique_together": {("entreprise_id", "type_evenement")},
            },
        ),
        migrations.CreateModel(
            name="EvenementMetier",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("entreprise_id", models.CharField(blank=True, db_index=True, default="", max_length=255)),
                ("type_evenement", models.CharField(db_index=True, max_length=100)),
                ("source_system", models.CharField(db_index=True, max_length=100)),
                ("source_type", models.CharField(blank=True, default="", max_length=100)),
                ("source_id", models.CharField(blank=True, db_index=True, default="", max_length=255)),
                ("idempotency_key", models.CharField(max_length=255)),
                ("payload", models.JSONField(default=dict)),
                ("statut", models.CharField(choices=[("RECU", "Reçu"), ("TRAITE", "Traité"), ("IGNORE", "Ignoré"), ("ERREUR", "Erreur")], db_index=True, default="RECU", max_length=20)),
                ("erreur", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("ecriture", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="evenements_sources", to="comptabilite_ohada.ecriturecomptable")),
            ],
            options={
                "verbose_name": "Événement métier",
                "verbose_name_plural": "Événements métier",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="ecriturecomptable",
            constraint=models.UniqueConstraint(
                condition=models.Q(("idempotency_key__isnull", False)),
                fields=("entreprise_id", "idempotency_key"),
                name="uniq_ecriture_idempotente_par_entreprise",
            ),
        ),
        migrations.AddConstraint(
            model_name="evenementmetier",
            constraint=models.UniqueConstraint(
                fields=("entreprise_id", "idempotency_key"),
                name="uniq_evenement_idempotent_par_entreprise",
            ),
        ),
    ]
