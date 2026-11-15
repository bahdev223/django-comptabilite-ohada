from datetime import date
from django.db import connection, IntegrityError, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class PolicyMigrationTests(TransactionTestCase):
    def test_upgrade_preserves_posted_history_and_does_not_classify_legacy(self):
        executor=MigrationExecutor(connection)
        # Resolve the actual historical leaf by dependency, never guess its name.
        node=executor.loader.get_migration('comptabilite_ohada','0007_accountingpolicyassignment')
        before=node.dependencies
        after=[('comptabilite_ohada','0007_accountingpolicyassignment')]
        executor.migrate(before)
        try:
            apps=executor.loader.project_state(before).apps
            Year=apps.get_model('comptabilite_ohada','ExerciceComptable')
            Journal=apps.get_model('comptabilite_ohada','JournalComptable')
            Account=apps.get_model('comptabilite_ohada','CompteComptable')
            Entry=apps.get_model('comptabilite_ohada','EcritureComptable')
            Line=apps.get_model('comptabilite_ohada','LigneEcritureComptable')
            year=Year.objects.create(entreprise_id='OLD',code='2025',date_debut=date(2025,1,1),date_fin=date(2025,12,31),cloture=True)
            journal=Journal.objects.create(entreprise_id='OLD',code='OD',libelle='Divers')
            entry=Entry.objects.create(entreprise_id='OLD',exercice=year,journal=journal,reference='OLD',date_ecriture=date(2025,1,1),libelle='Historique',validee=True)
            for code,debit,credit in [('571',100,0),('101',0,100)]:
                account=Account.objects.create(entreprise_id='OLD',code=code,libelle=code)
                Line.objects.create(ecriture=entry,compte=account,debit=debit,credit=credit)
            original=list(Line.objects.order_by('pk').values())
            executor=MigrationExecutor(connection);executor.migrate(after)
            apps=executor.loader.project_state(after).apps
            self.assertEqual(original,list(apps.get_model('comptabilite_ohada','LigneEcritureComptable').objects.order_by('pk').values()))
            self.assertFalse(apps.get_model('comptabilite_ohada','AccountingPolicyAssignment').objects.exists())
            self.assertTrue(apps.get_model('comptabilite_ohada','ExerciceComptable').objects.get(pk=year.pk).cloture)
            self.assertTrue(apps.get_model('comptabilite_ohada','EcritureComptable').objects.get(pk=entry.pk).validee)
        finally:
            executor=MigrationExecutor(connection);executor.migrate(executor.loader.graph.leaf_nodes())

    def test_database_enforces_one_valid_policy_per_exercise(self):
        from comptabilite_ohada.models import ExerciceComptable
        from comptabilite_ohada.services import accounting_policy_service as service
        from .test_accounting_policy import decision
        year=ExerciceComptable.objects.create(entreprise_id='DB',code='2026',date_debut=date(2026,1,1),date_fin=date(2026,12,31))
        service.prepare(year,system='NORMAL',decision=decision(),entreprise_id='DB')
        table='comptabilite_ohada_accountingpolicyassignment'
        for sql in [f"UPDATE {table} SET system='OTHER'", f"UPDATE {table} SET status='confirmed'", f"UPDATE {table} SET frozen_at=CURRENT_TIMESTAMP"]:
            with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(sql)
        with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(f"INSERT INTO {table} (exercise_id,system,ruleset_version,status,decision,revision) SELECT exercise_id,system,ruleset_version,status,decision,revision FROM {table}")
