import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("comptabilite_ohada", "0010_config_fiscal_api_clients"),
    ]

    operations = [
        migrations.AlterField(
            model_name="comptecomptable",
            name="parent",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="enfants",
                to="comptabilite_ohada.comptecomptable",
                verbose_name="Compte parent",
            ),
        ),
    ]
