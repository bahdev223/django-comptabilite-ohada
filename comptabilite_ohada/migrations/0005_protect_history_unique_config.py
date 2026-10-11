"""Protect accounting history and enforce unique nonempty tenant configuration.

Do not apply to a production database before auditing pre-existing tenant IDs
and rehearsing the migration on a restored PostgreSQL copy.
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("comptabilite_ohada", "0004_tenant_auxiliary_models"),
    ]

    operations = [
        migrations.AlterField(
            model_name="ecriturecomptable",
            name="journal",
            field=models.ForeignKey(
                to="comptabilite_ohada.journalcomptable",
                on_delete=django.db.models.deletion.PROTECT,
                verbose_name="Journal",
            ),
        ),
        migrations.AlterField(
            model_name="ecriturecomptable",
            name="exercice",
            field=models.ForeignKey(
                to="comptabilite_ohada.exercicecomptable",
                on_delete=django.db.models.deletion.PROTECT,
                verbose_name="Exercice",
            ),
        ),
        migrations.AlterField(
            model_name="ligneecriturecomptable",
            name="ecriture",
            field=models.ForeignKey(
                to="comptabilite_ohada.ecriturecomptable",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="lignes",
                verbose_name="Écriture",
            ),
        ),
        migrations.AlterField(
            model_name="ligneecriturecomptable",
            name="compte",
            field=models.ForeignKey(
                to="comptabilite_ohada.comptecomptable",
                on_delete=django.db.models.deletion.PROTECT,
                verbose_name="Compte",
            ),
        ),
        migrations.AddConstraint(
            model_name="configurationcomptable",
            constraint=models.UniqueConstraint(
                fields=("entreprise_id",),
                condition=~models.Q(entreprise_id=""),
                name="ohada_config_tenant_nonempty_unique",
            ),
        ),
    ]
