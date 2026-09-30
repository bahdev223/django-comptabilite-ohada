# Generated for tenant hardening.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("comptabilite_ohada", "0003_alter_comptecomptable_categorie"),
    ]

    operations = [
        migrations.AddField(
            model_name="configurationcomptable",
            name="entreprise_id",
            field=models.CharField(blank=True, db_index=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="immobilisation",
            name="entreprise_id",
            field=models.CharField(blank=True, db_index=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="relevebancaire",
            name="entreprise_id",
            field=models.CharField(blank=True, db_index=True, default="", max_length=255),
        ),
        migrations.AlterField(
            model_name="immobilisation",
            name="code",
            field=models.CharField(max_length=20, verbose_name="Code"),
        ),
        migrations.AlterUniqueTogether(
            name="immobilisation",
            unique_together={("entreprise_id", "code")},
        ),
    ]
