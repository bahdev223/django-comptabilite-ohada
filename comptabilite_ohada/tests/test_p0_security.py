from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, ImproperlyConfigured
from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from ..models import CompteComptable, JournalComptable, ExerciceComptable, EcritureComptable, ConfigurationComptable
from ..services.ecriture_service import EcritureService
from ..services.journal_service import BalanceService, GrandLivreService
from ..services.bilan_service import BilanService
from ..services.dashboard_service import DashboardService
from ..services.initialisation_service import InitialisationService
from ..services.exercice_service import ValidationService


class EnterpriseSecurityTests(TestCase):
    def setUp(self):
        self.rows = {}
        for tenant in ('A', 'B'):
            self.rows[tenant] = {
                'journal': JournalComptable.objects.create(entreprise_id=tenant, code='CS', libelle='Caisse', type_journal='CAISSE'),
                'exercice': ExerciceComptable.objects.create(entreprise_id=tenant, code='2026', date_debut=date(2026, 1, 1), date_fin=date(2026, 12, 31)),
                'cash': CompteComptable.objects.create(entreprise_id=tenant, code='571', libelle='Caisse'),
                'bank': CompteComptable.objects.create(entreprise_id=tenant, code='521', libelle='Banque'),
                'client': CompteComptable.objects.create(entreprise_id=tenant, code='411', libelle='Clients'),
                'sale': CompteComptable.objects.create(entreprise_id=tenant, code='706', libelle='Ventes'),
            }

    def create(self, tenant='A', **overrides):
        r = self.rows[tenant]
        data = dict(reference='TEST', date_ecriture=date(2026, 6, 1), libelle='Test',
                    journal=r['journal'], exercice=r['exercice'], entreprise_id=tenant,
                    lignes=[{'compte': r['cash'], 'debit': Decimal('10')}, {'compte': r['client'], 'credit': Decimal('10')}])
        data.update(overrides)
        return EcritureService.creer_ecriture(**data)

    def test_lookup_requires_enterprise(self):
        with self.assertRaises(ValidationError):
            EcritureService.get_compte('571')


    def test_text_account_code_cannot_be_mistaken_for_pk(self):
        from ..models import CompteComptable
        account = CompteComptable.objects.create(
            entreprise_id='A', code='999', libelle='Compte interne',
        )
        numeric_pk_text = str(account.pk)
        # When no code with these digits exists, the code lookup must not
        # expose the record by its PK.
        if numeric_pk_text != account.code and not CompteComptable.objects.filter(
            entreprise_id='A', code=numeric_pk_text
        ).exists():
            self.assertIsNone(
                EcritureService.get_compte(numeric_pk_text, entreprise_id='A')
            )

    def test_closure_default_fails_closed_without_an_audited_syscohada_process(self):
        from ..services.exercice_service import ExerciceService
        with self.assertRaises(ValidationError):
            ExerciceService.cloturer(
                self.rows['A']['exercice'], entreprise_id='A'
            )
        self.rows['A']['exercice'].refresh_from_db()
        self.assertFalse(self.rows['A']['exercice'].cloture)

    def test_lookup_never_returns_foreign_account(self):
        self.assertEqual(EcritureService.get_compte('571', entreprise_id='B'), self.rows['B']['cash'])
        self.assertIsNone(EcritureService.get_compte(self.rows['B']['cash'].pk, entreprise_id='A'))

    def test_no_exercise_fallback_outside_dates(self):
        self.assertIsNone(EcritureService.get_exercice(date(2027, 1, 1), entreprise_id='A'))

    def test_valid_entry_is_scoped_and_timestamped(self):
        entry = self.create()
        self.assertEqual(entry.entreprise_id, 'A')
        self.assertIsNotNone(entry.date_validation)
        self.assertEqual(entry.total_debit, Decimal('10'))

    def test_foreign_journal_exercise_and_account_rejected_atomically(self):
        for overrides in ({'journal': self.rows['B']['journal']}, {'exercice': self.rows['B']['exercice']},
                          {'lignes': [{'compte': self.rows['B']['cash'], 'debit': 10}, {'compte': self.rows['A']['client'], 'credit': 10}]}):
            with self.subTest(overrides=overrides), self.assertRaises(ValidationError):
                self.create(**overrides)
        self.assertEqual(EcritureComptable.objects.count(), 0)

    def test_closed_or_out_of_period_exercise_rejected(self):
        self.rows['A']['exercice'].cloture = True
        self.rows['A']['exercice'].save()
        with self.assertRaises(ValidationError):
            self.create()
        with self.assertRaises(ValidationError):
            self.create('B', date_ecriture=date(2027, 1, 1))

    def test_invalid_amounts_rejected_before_writes(self):
        for debit, credit in ((-10, -10), ('0.001', '0.001'), ('NaN', 'NaN'), ('Infinity', 'Infinity'), (0, 0), ('10000000000000', '10000000000000')):
            with self.subTest(debit=debit), self.assertRaises(ValidationError):
                self.create(lignes=[{'compte': self.rows['A']['cash'], 'debit': debit}, {'compte': self.rows['A']['client'], 'credit': credit}])
        self.assertFalse(EcritureComptable.objects.exists())

    def test_dual_sided_line_rejected(self):
        with self.assertRaises(ValidationError):
            self.create(lignes=[{'compte': self.rows['A']['cash'], 'debit': 10, 'credit': 10}])

    def test_inactive_account_rejected_even_with_stale_instance(self):
        CompteComptable.objects.filter(pk=self.rows['A']['cash'].pk).update(actif=False)
        with self.assertRaises(ValidationError):
            self.create()

    def test_reports_are_scoped(self):
        self.create('A')
        self.create('B')
        self.assertEqual(sum(r['total_debit'] for r in BalanceService.balance(entreprise_id='A')), Decimal('10'))
        self.assertEqual(len(GrandLivreService.grand_livre(entreprise_id='A')), 2)
        self.assertEqual(DashboardService.synthese(entreprise_id='A')['nb_ecritures'], 1)
        BilanService.bilan(entreprise_id='A')
        with self.assertRaises(ValidationError):
            BalanceService.balance(exercice=self.rows['B']['exercice'], entreprise_id='A')
        with self.assertRaises(ValidationError):
            BalanceService.balance()

    def test_selector_and_csv_are_scoped(self):
        from ..selectors import ComptabiliteSelector
        from ..services.export_service import ExportService
        self.create('A', reference='A-REF')
        self.create('B', reference='B-REF')
        selector = ComptabiliteSelector(entreprise_id='A')
        self.assertEqual(selector.ecritures_par_compte('571').count(), 1)
        self.assertEqual(selector.ecritures_non_validees().count(), 0)
        csv = ExportService.export_ecritures_csv(entreprise_id='A').content.decode()
        self.assertIn('A-REF', csv)
        self.assertNotIn('B-REF', csv)

    def test_reversal_cancels_dashboard_profit(self):
        original = self.create(lignes=[{'compte': self.rows['A']['cash'], 'debit': 10}, {'compte': self.rows['A']['sale'], 'credit': 10}])
        ValidationService.annuler_ecriture(original, entreprise_id='A', raison='Erreur', date_operation=date(2026, 6, 2))
        self.assertEqual(DashboardService.synthese(entreprise_id='A')['resultat'], Decimal('0'))

    def test_reversal_then_closure_posts_no_fictitious_profit(self):
        from ..services.exercice_service import ExerciceService
        original = self.create(lignes=[{'compte': self.rows['A']['cash'], 'debit': 10}, {'compte': self.rows['A']['sale'], 'credit': 10}])
        ValidationService.annuler_ecriture(original, entreprise_id='A', raison='Erreur', date_operation=date(2026, 6, 2))
        with self.assertRaises(ValidationError):
            ExerciceService.cloturer(self.rows['A']['exercice'], entreprise_id='A')
        self.rows['A']['exercice'].refresh_from_db()
        self.assertFalse(self.rows['A']['exercice'].cloture)
        self.assertFalse(EcritureComptable.objects.filter(reference='RES-2026').exists())

    def test_closed_exercise_cannot_receive_direct_draft(self):
        self.rows['A']['exercice'].cloture = True
        self.rows['A']['exercice'].save()
        with self.assertRaises(ValidationError):
            EcritureComptable.objects.create(entreprise_id='A', reference='CLOSED', date_ecriture=date(2026, 6, 1), libelle='Draft', journal=self.rows['A']['journal'], exercice=self.rows['A']['exercice'])

    def test_explicit_read_serializers_are_usable(self):
        from ..api.serializers import EcritureComptableSerializer
        data = EcritureComptableSerializer(self.create()).data
        self.assertEqual(len(data['lignes']), 2)
        self.assertEqual(Decimal(data['total_debit']), Decimal('10'))

    def test_configuration_does_not_reuse_legacy_singleton(self):
        legacy = ConfigurationComptable.objects.create(pk=1)
        a = ConfigurationComptable.get_config(entreprise_id='A')
        b = ConfigurationComptable.get_config(entreprise_id='B')
        self.assertNotEqual(a.pk, b.pk)
        self.assertNotEqual(a.pk, legacy.pk)

    def test_force_chart_reload_preserves_historical_entries(self):
        self.create()
        InitialisationService.charger_plan_comptable(force=True, entreprise_id='A')
        self.assertEqual(EcritureComptable.objects.count(), 1)
        self.assertTrue(CompteComptable.objects.filter(pk=self.rows['B']['cash'].pk).exists())

    def test_opening_balance_cannot_inject_identity_or_negative_amount(self):
        from ..models import SoldeInitialComptable
        b = ConfigurationComptable.get_config(entreprise_id='B')
        for payload in ({'caisse': 10, 'configuration_id': b.pk}, {'id': 999, 'caisse': 10}, {'caisse': -10}):
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                InitialisationService.initialiser_soldes(payload, entreprise_id='A')
        self.assertEqual(SoldeInitialComptable.objects.count(), 0)

    def test_transfer_has_no_income_account(self):
        e = EcritureService.creer_ecriture_transfert('571', '521', 10, 'Virement', entreprise_id='A')
        self.assertEqual(set(e.lignes.values_list('compte__code', flat=True)), {'571', '521'})
        self.assertEqual(e.entreprise_id, 'A')
        for destination in ('706', '571'):
            with self.assertRaises(ValidationError):
                EcritureService.creer_ecriture_transfert('571', destination, 10, 'Virement', entreprise_id='A')

    def test_receipt_settles_client_without_creating_sale(self):
        e = EcritureService.creer_ecriture_encaissement('571', 10, 'Règlement', '411', entreprise_id='A')
        self.assertEqual(set(e.lignes.values_list('compte__code', flat=True)), {'571', '411'})
        with self.assertRaises(ValidationError):
            EcritureService.creer_ecriture_encaissement('571', 10, 'Non qualifié', '706', entreprise_id='A')

    def test_validation_rechecks_closed_exercise(self):
        e = self.create(validee=False)
        ExerciceComptable.objects.filter(pk=e.exercice_id).update(cloture=True)
        with self.assertRaises(ValidationError):
            ValidationService.valider_ecriture(e, entreprise_id='A')
        e.refresh_from_db()
        self.assertFalse(e.validee)

    def test_posted_entry_and_lines_cannot_be_changed_or_deleted(self):
        e = self.create()
        e.libelle = 'Réécriture'
        with self.assertRaises(ValidationError):
            e.save()
        with self.assertRaises(ValidationError):
            e.delete()
        line = e.lignes.first()
        line.debit = Decimal('2')
        with self.assertRaises(ValidationError):
            line.save()
        with self.assertRaises(ValidationError):
            line.delete()

    def test_direct_validation_requires_domain(self):
        e = self.create(validee=False)
        e.validee = True
        with self.assertRaises(ValidationError):
            e.save()

    def test_bulk_mutation_and_cascade_deletion_cannot_erase_posted_history(self):
        from django.db.models.deletion import ProtectedError
        entry = self.create()
        with self.assertRaises(ValidationError):
            EcritureComptable.objects.filter(pk=entry.pk).delete()
        with self.assertRaises(ValidationError):
            EcritureComptable.objects.filter(pk=entry.pk).update(libelle='Écrasé')
        with self.assertRaises(ValidationError):
            entry.lignes.all().update(debit=0)
        with self.assertRaises(ProtectedError):
            self.rows['A']['cash'].delete()

    def test_new_empty_tenant_entry_rejected(self):
        with self.assertRaises(ValidationError):
            EcritureComptable.objects.create(reference='ORPHAN', date_ecriture=date(2026, 6, 1), libelle='Orphan', journal=self.rows['A']['journal'], exercice=self.rows['A']['exercice'])

    def test_unvalidated_secondary_services_fail_closed(self):
        from ..services.rapprochement_service import RapprochementService
        from ..services.amortissement_service import AmortissementService
        with self.assertRaises(ImproperlyConfigured):
            RapprochementService.creer_releve('521', date(2026, 1, 1), date(2026, 1, 31), 0, 0)
        with self.assertRaises(ImproperlyConfigured):
            AmortissementService.generer_ecritures_amortissement()

    def test_reversal_preserves_original_and_is_not_duplicated(self):
        original = self.create()
        reversal = ValidationService.annuler_ecriture(original, entreprise_id='A', raison='Erreur', date_operation=date(2026, 6, 2))
        self.assertEqual(reversal.total_debit, original.total_credit)
        self.assertEqual(reversal.lignes.get(compte=self.rows['A']['cash']).credit, Decimal('10'))
        original.refresh_from_db()
        self.assertTrue(original.validee)
        with self.assertRaises(ValidationError):
            ValidationService.annuler_ecriture(original, entreprise_id='A', raison='Encore', date_operation=date(2026, 6, 2))

    def test_staff_is_not_accounting_authorization(self):
        from ..permissions import has_compta_permission
        user = get_user_model().objects.create_user('staff', is_staff=True)
        self.assertFalse(has_compta_permission(user, 'compta_validate'))

    def test_all_legacy_api_viewsets_deny_even_superuser(self):
        from ..api import views
        user = get_user_model().objects.create_user('root', is_superuser=True)
        for name in ('CompteComptableViewSet', 'EcritureComptableViewSet', 'JournalComptableViewSet', 'ExerciceComptableViewSet', 'ConfigurationComptableViewSet', 'ImmobilisationViewSet'):
            for method, action in (('get', 'list'), ('post', 'create')):
                request = getattr(APIRequestFactory(), method)('/', {}, format='json')
                force_authenticate(request, user=user)
                self.assertEqual(getattr(views, name).as_view({method: action})(request).status_code, 403)

    def test_legacy_creation_serializer_is_blocked(self):
        from ..api.serializers import EcritureCreateSerializer
        with self.assertRaises(Exception):
            EcritureCreateSerializer().create(dict(reference='BYPASS', date_ecriture=date(2026, 6, 1), libelle='Bypass', journal=self.rows['A']['journal'], exercice=self.rows['A']['exercice'], lignes=[]))
        self.assertFalse(EcritureComptable.objects.exists())

    @override_settings(COMPTABILITE_OHADA={'COMPTES_INTEGRATION_ENABLED': True})
    def test_unsafe_signal_bridge_cannot_be_enabled(self):
        from ..integrations import connect_integrations
        with self.assertRaises(ImproperlyConfigured):
            connect_integrations()
