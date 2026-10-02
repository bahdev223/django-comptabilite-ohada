from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("comptabilite_ohada", "0008_line_integrity_constraints"),
    ]

    operations = [
        migrations.AddField(
            model_name="configurationcomptable",
            name="compte_mobile_money_defaut",
            field=models.CharField(default="552", max_length=20, verbose_name="Compte Mobile Money défaut"),
        ),
    ]
