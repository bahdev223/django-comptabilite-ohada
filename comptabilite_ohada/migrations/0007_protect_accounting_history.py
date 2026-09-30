import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("comptabilite_ohada", "0006_standalone_tenant_registry"),
    ]

    operations = [
        migrations.AlterField(
            model_name="ecriturecomptable",
            name="journal",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                to="comptabilite_ohada.journalcomptable",
                verbose_name="Journal",
            ),
        ),
        migrations.AlterField(
            model_name="ecriturecomptable",
            name="exercice",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                to="comptabilite_ohada.exercicecomptable",
                verbose_name="Exercice",
            ),
        ),
        migrations.AlterField(
            model_name="ligneecriturecomptable",
            name="compte",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                to="comptabilite_ohada.comptecomptable",
                verbose_name="Compte",
            ),
        ),
    ]
