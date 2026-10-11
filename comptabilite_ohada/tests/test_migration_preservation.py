from datetime import date
from decimal import Decimal

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class HistoricalMigrationTests(TransactionTestCase):
    def test_additive_tenant_migration_preserves_orphaned_history(self):
        before = [('comptabilite_ohada', '0003_alter_comptecomptable_categorie')]
        after = [('comptabilite_ohada', '0005_alter_ecriturecomptable_exercice_and_more')]
        executor = MigrationExecutor(connection)
        executor.migrate(before)
        apps = executor.loader.project_state(before).apps
        Journal = apps.get_model('comptabilite_ohada', 'JournalComptable')
        Exercise = apps.get_model('comptabilite_ohada', 'ExerciceComptable')
        Account = apps.get_model('comptabilite_ohada', 'CompteComptable')
        Entry = apps.get_model('comptabilite_ohada', 'EcritureComptable')
        Line = apps.get_model('comptabilite_ohada', 'LigneEcritureComptable')
        Config = apps.get_model('comptabilite_ohada', 'ConfigurationComptable')
        Immo = apps.get_model('comptabilite_ohada', 'Immobilisation')
        journal = Journal.objects.create(code='OLD', libelle='Ancien', type_journal='OD')
        exercise = Exercise.objects.create(code='2025', date_debut=date(2025, 1, 1), date_fin=date(2025, 12, 31))
        account = Account.objects.create(code='571', libelle='Historique')
        entry = Entry.objects.create(reference='OLD-1', journal=journal, exercice=exercise, date_ecriture=date(2025, 6, 1), libelle='Historique', validee=True)
        line = Line.objects.create(ecriture=entry, compte=account, debit=Decimal('100.00'))
        config = Config.objects.create(nom='Configuration ancienne')
        immo = Immo.objects.create(code='OLD-ASSET', libelle='Actif ancien', type_immobilisation='CORPORELLE', date_acquisition=date(2025, 1, 1), valeur_originale=100, duree_ans=5, compte_immobilisation=account, compte_amortissement=account, compte_charge=account)
        try:
            executor = MigrationExecutor(connection)
            executor.migrate(after)
            apps = executor.loader.project_state(after).apps
            for model, pk in (('EcritureComptable', entry.pk), ('ConfigurationComptable', config.pk), ('Immobilisation', immo.pk)):
                self.assertEqual(apps.get_model('comptabilite_ohada', model).objects.get(pk=pk).entreprise_id, '')
            self.assertEqual(apps.get_model('comptabilite_ohada', 'LigneEcritureComptable').objects.get(pk=line.pk).debit, Decimal('100.00'))
            self.assertTrue(apps.get_model('comptabilite_ohada', 'EcritureComptable').objects.get(pk=entry.pk).validee)
        finally:
            MigrationExecutor(connection).migrate(after)
