"""Regression tests for secondary entry points and historical preservation."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from ..models import CompteComptable, EcritureComptable, ExerciceComptable, JournalComptable, LigneEcritureComptable
from ..services.ecriture_service import EcritureService
from ..services.dashboard_service import DashboardService
from ..services.journal_service import BalanceService
from ..services.exercice_service import ValidationService


class ReviewSecurityTests(TestCase):
    def setUp(self):
        self.year = ExerciceComptable.objects.create(entreprise_id='A', code='2026', date_debut=date(2026, 1, 1), date_fin=date(2026, 12, 31))
        self.journal = JournalComptable.objects.create(entreprise_id='A', code='OD', libelle='OD', type_journal='OD')
        self.cash = CompteComptable.objects.create(entreprise_id='A', code='571', libelle='Cash')
        self.other = CompteComptable.objects.create(entreprise_id='A', code='411', libelle='Clients')

    def test_base_collector_cannot_cascade_delete_ledger_lines(self):
        entry = EcritureService.creer_ecriture('PRESERVE', date(2026, 1, 1), 'Preserve', self.journal, [dict(compte=self.cash, debit=Decimal('10')), dict(compte=self.other, credit=Decimal('10'))], exercice=self.year, entreprise_id='A')
        with self.assertRaises(ProtectedError):
            models.QuerySet(model=EcritureComptable).filter(pk=entry.pk).delete()
        self.assertEqual(LigneEcritureComptable.objects.filter(ecriture=entry).count(), 2)

    def test_secondary_closure_entry_point_is_suspended(self):
        with self.assertRaisesRegex(ValidationError, 'suspend'):
            EcritureService.creer_ecriture_cloture_exercice(self.year, Decimal('100'), entreprise_id='A')
        self.assertFalse(EcritureComptable.objects.exists())

    def test_secondary_amortization_entry_point_is_suspended(self):
        with self.assertRaisesRegex(ValidationError, 'suspend'):
            EcritureService.creer_ecriture_amortissement(SimpleNamespace(), entreprise_id='A')
        self.assertFalse(EcritureComptable.objects.exists())

    def test_line_with_inactive_account_is_refused(self):
        entry = EcritureService.creer_ecriture('DRAFT', date(2026, 1, 1), 'Draft', self.journal, [dict(compte=self.cash, debit=Decimal('10')), dict(compte=self.other, credit=Decimal('10'))], exercice=self.year, entreprise_id='A', validee=False)
        CompteComptable.objects.filter(pk=self.cash.pk).update(actif=False)
        with self.assertRaises(ValidationError):
            LigneEcritureComptable.objects.create(ecriture=entry, compte=self.cash, debit=Decimal('1'))

    def create_entry(self, reference, exercise=None):
        return EcritureService.creer_ecriture(reference, date(2026, 1, 1), 'Entry', self.journal, [dict(compte=self.cash, debit=Decimal('10')), dict(compte=self.other, credit=Decimal('10'))], exercice=exercise or self.year, entreprise_id='A')

    def test_dashboard_does_not_disclose_foreign_journal_from_legacy_graph(self):
        entry = self.create_entry('LEGACY-GRAPH')
        foreign = JournalComptable.objects.create(entreprise_id='B', code='SECRET-B', libelle='Private B', type_journal='OD')
        models.QuerySet(model=EcritureComptable).filter(pk=entry.pk).update(journal=foreign)
        self.assertEqual(list(DashboardService.dernieres_ecritures(entreprise_id='A')), [])
        self.assertEqual(list(DashboardService.totaux_par_journal(entreprise_id='A')), [])

    def test_explicit_exercise_does_not_mix_overlapping_legacy_periods(self):
        other_year = ExerciceComptable.objects.create(entreprise_id='A', code='LEGACY-OVERLAP', date_debut=self.year.date_debut, date_fin=self.year.date_fin)
        self.create_entry('YEAR-1')
        self.create_entry('YEAR-2', other_year)
        balance = BalanceService.balance(exercice=self.year, entreprise_id='A')
        self.assertEqual(sum(row['total_debit'] for row in balance), Decimal('10'))

    def test_ambiguous_automatic_exercise_is_refused(self):
        ExerciceComptable.objects.create(entreprise_id='A', code='LEGACY-OVERLAP', date_debut=self.year.date_debut, date_fin=self.year.date_fin)
        with self.assertRaises(ValidationError):
            EcritureService.get_exercice(date(2026, 1, 1), entreprise_id='A')

    def test_reversal_into_new_year_preserves_closed_original(self):
        entry = self.create_entry('CLOSED-ORIGINAL')
        ExerciceComptable.objects.filter(pk=self.year.pk).update(cloture=True)
        next_year = ExerciceComptable.objects.create(entreprise_id='A', code='2027', date_debut=date(2027, 1, 1), date_fin=date(2027, 12, 31))
        reversal = ValidationService.annuler_ecriture(entry, raison='Pièce rectifiée', entreprise_id='A', date_operation=date(2027, 1, 2))
        entry.refresh_from_db()
        self.assertTrue(entry.validee)
        self.assertEqual(reversal.exercice_id, next_year.pk)
        with self.assertRaises(ValidationError):
            ValidationService.annuler_ecriture(entry, raison='Répétition', entreprise_id='A', date_operation=date(2027, 1, 2))
