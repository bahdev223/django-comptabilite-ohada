from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("comptabilite_ohada", "0007_protect_accounting_history"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="ligneecriturecomptable",
            constraint=models.CheckConstraint(
                condition=models.Q(("credit__gte", 0), ("debit__gte", 0)),
                name="ligne_montants_non_negatifs",
            ),
        ),
        migrations.AddConstraint(
            model_name="ligneecriturecomptable",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(("credit", 0), ("debit__gt", 0))
                    | models.Q(("credit__gt", 0), ("debit", 0))
                ),
                name="ligne_exactement_un_sens",
            ),
        ),
    ]
