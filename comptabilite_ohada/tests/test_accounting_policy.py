from datetime import date
from django.core.exceptions import ValidationError
from django.test import TestCase
from comptabilite_ohada.models import (CompteComptable, JournalComptable,
    ExerciceComptable, EcritureComptable)
from comptabilite_ohada.services.ecriture_service import EcritureService
from comptabilite_ohada.services.exercice_service import ValidationService
from comptabilite_ohada.services import accounting_policy_service as policies


def decision():
    return {'country': 'ML', 'activity': 'Commerce', 'currency': 'XOF',
            'basis': 'normal_option', 'source': 'Décision du responsable comptable',
            'reason': 'Option explicite pour la comptabilité complète.',
            'confirmed': True}


class AccountingPolicyTests(TestCase):
    def setUp(self):
        self.year = ExerciceComptable.objects.create(entreprise_id='A', code='2026',
            date_debut=date(2026, 1, 1), date_fin=date(2026, 12, 31))
        self.journal = JournalComptable.objects.create(entreprise_id='A', code='OD', libelle='Divers')
        self.cash = CompteComptable.objects.create(entreprise_id='A', code='571', libelle='Caisse')
        self.capital = CompteComptable.objects.create(entreprise_id='A', code='101', libelle='Capital')

    def entry(self, posted=True, ref='E1'):
        return EcritureService.creer_ecriture(reference=ref, date_ecriture=date(2026, 2, 1),
            libelle='Apport', journal=self.journal, exercice=self.year, entreprise_id='A',
            lignes=[{'compte': self.cash, 'debit': 100}, {'compte': self.capital, 'credit': 100}],
            validee=posted)

    def prepare(self, system='NORMAL'):
        return policies.prepare(self.year, system=system, decision=decision(), entreprise_id='A')

    def confirmed(self):
        p = self.prepare()
        return policies.confirm(self.year, fingerprint=p['fingerprint'], entreprise_id='A')

    def test_legacy_read_does_not_classify_or_block_existing_posting(self):
        from comptabilite_ohada.models import AccountingPolicyAssignment
        self.assertEqual(policies.policy_status(self.year, entreprise_id='A')['status'], 'legacy_unclassified')
        self.assertFalse(AccountingPolicyAssignment.objects.exists())
        self.assertTrue(self.entry().validee)
        self.assertFalse(AccountingPolicyAssignment.objects.exists())

    def test_foreign_exercise_cannot_be_read_or_prepared(self):
        with self.assertRaises(ValidationError):
            policies.policy_status(self.year, entreprise_id='B')
        with self.assertRaises(ValidationError):
            policies.prepare(self.year, system='NORMAL', decision=decision(), entreprise_id='B')

    def test_draft_blocks_both_direct_posting_and_draft_validation(self):
        self.prepare()
        with self.assertRaises(ValidationError): self.entry()
        self.assertFalse(EcritureComptable.objects.exists())
        draft = self.entry(posted=False)
        with self.assertRaises(ValidationError):
            ValidationService.valider_ecriture(draft, entreprise_id='A')
        draft.refresh_from_db(); self.assertFalse(draft.validee)

    def test_confirmation_freezes_only_when_first_validated_entry_succeeds(self):
        p = self.confirmed()
        self.assertEqual(p['status'], 'confirmed')
        self.assertIsNone(p['frozen_at'])
        self.entry(posted=False)
        self.assertIsNone(policies.policy_status(self.year, entreprise_id='A')['frozen_at'])
        self.entry(ref='E2')
        self.assertIsNotNone(policies.policy_status(self.year, entreprise_id='A')['frozen_at'])
        with self.assertRaises(ValidationError): self.prepare()

    def test_existing_posted_legacy_requires_controlled_reprise(self):
        self.entry()
        with self.assertRaises(ValidationError): self.prepare()
        self.assertEqual(policies.policy_status(self.year, entreprise_id='A')['status'], 'legacy_unclassified')

    def test_smt_can_be_prepared_but_never_confirmed_or_posted(self):
        p = self.prepare('SMT')
        with self.assertRaises(ValidationError):
            policies.confirm(self.year, fingerprint=p['fingerprint'], entreprise_id='A')
        with self.assertRaises(ValidationError): self.entry()

    def test_stale_confirmation_cannot_confirm_another_decision(self):
        first = self.prepare()
        changed = decision(); changed['reason'] = 'Nouvelle décision documentée par le responsable.'
        policies.prepare(self.year, system='NORMAL', decision=changed, entreprise_id='A')
        with self.assertRaises(ValidationError):
            policies.confirm(self.year, fingerprint=first['fingerprint'], entreprise_id='A')

    def test_same_confirmation_is_idempotent(self):
        p = self.confirmed()
        again = policies.confirm(self.year, fingerprint=p['fingerprint'], entreprise_id='A')
        self.assertEqual(p, again)

    def test_invalid_or_missing_decision_and_system_are_rejected(self):
        for system, data in [('OTHER', decision()), ('NORMAL', {}), ('NORMAL', {'country':'ML'})]:
            with self.subTest(system=system, data=data), self.assertRaises(ValidationError):
                policies.prepare(self.year, system=system, decision=data, entreprise_id='A')

    def test_model_and_bulk_mutations_cannot_erase_frozen_decision(self):
        from comptabilite_ohada.models import AccountingPolicyAssignment
        self.confirmed(); self.entry()
        p = AccountingPolicyAssignment.objects.get(exercise=self.year)
        p.system = 'SMT'
        with self.assertRaises(ValidationError): p.save()
        with self.assertRaises(ValidationError): p.delete()
        with self.assertRaises(ValidationError): AccountingPolicyAssignment.objects.all().update(status='draft')
        with self.assertRaises(ValidationError): AccountingPolicyAssignment.objects.all().delete()

    def test_unknown_ruleset_cannot_post_even_if_row_was_incorrectly_imported(self):
        from django.db import models
        from comptabilite_ohada.models import AccountingPolicyAssignment
        self.confirmed()
        models.QuerySet(model=AccountingPolicyAssignment).filter(exercise=self.year).update(ruleset_version='unknown')
        with self.assertRaises(ValidationError): self.entry()

    def test_closed_year_cannot_receive_a_decision(self):
        self.year.cloture = True; self.year.save()
        with self.assertRaises(ValidationError): self.prepare()
