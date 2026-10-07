#!/usr/bin/env python3
"""Verify 0003 -> canonical leaf with historical entries on a disposable DB."""
import os
from pathlib import Path
import sys
import tempfile


def main():
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo))
    with tempfile.TemporaryDirectory(prefix="ohada-migrations-") as directory:
        os.environ.update(DJANGO_SETTINGS_MODULE="standalone.settings",
                          DB_ENGINE="django.db.backends.sqlite3",
                          DB_NAME=str(Path(directory) / "upgrade.sqlite3"), COMPTES_INTEGRATION_ENABLED="0")
        import django
        django.setup()
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor
        old = ("comptabilite_ohada", "0003_alter_comptecomptable_categorie")
        expected_leaf = ("comptabilite_ohada", "0011_protect_account_parent")
        executor = MigrationExecutor(connection)
        assert executor.loader.graph.leaf_nodes("comptabilite_ohada") == [expected_leaf]
        executor.migrate([old])
        state = executor.loader.project_state([old]).apps
        model = lambda name: state.get_model("comptabilite_ohada", name)
        expense = model("CompteComptable").objects.create(entreprise_id="HISTORY", code="658",
                     libelle="Charges historiques", nature="CHARGE", sens="DEBIT")
        cash = model("CompteComptable").objects.create(entreprise_id="HISTORY", code="571",
                     libelle="Caisse historique", nature="ACTIF", sens="DEBIT")
        journal = model("JournalComptable").objects.create(entreprise_id="HISTORY", code="OD",
                     libelle="OD", type_journal="OD")
        year = model("ExerciceComptable").objects.create(entreprise_id="HISTORY", code="2026",
                     date_debut="2026-01-01", date_fin="2026-12-31")
        entry = model("EcritureComptable").objects.create(entreprise_id="HISTORY", reference="HIST-001",
                     date_ecriture="2026-06-01", libelle="Historical posting", journal=journal,
                     exercice=year, validee=True)
        for account, debit, credit in ((expense, 100, 0), (cash, 0, 100)):
            model("LigneEcritureComptable").objects.create(ecriture=entry, compte=account,
                                                          debit=debit, credit=credit, libelle="History")
        MigrationExecutor(connection).migrate([expected_leaf])
        from comptabilite_ohada.models import EcritureComptable, EvenementMetier, DimensionAnalytique
        migrated = EcritureComptable.objects.get(pk=entry.pk)
        assert migrated.entreprise_id == "HISTORY" and migrated.validee
        assert migrated.est_equilibree and migrated.total_debit == migrated.total_credit == 100
        assert migrated.lignes.count() == 2 and migrated.idempotency_key is None
        assert not EvenementMetier.objects.exists() and not DimensionAnalytique.objects.exists()
        executor = MigrationExecutor(connection)
        assert not executor.migration_plan([expected_leaf])
        assert len([name for name in executor.loader.applied_migrations
                    if name[0] == "comptabilite_ohada"]) == 11
        print(f"PASS Python {sys.version.split()[0]}: 0003 -> 0011, single leaf, historical entry + 2 lines preserved")


if __name__ == "__main__":
    main()
