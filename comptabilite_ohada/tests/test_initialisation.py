from django.test import TestCase
from django.db import connection
from django.test.utils import CaptureQueriesContext

from ..models import (
    CompteComptable,
)
from ..services.initialisation_service import InitialisationService


class InitialisationServiceTest(TestCase):
    def setUp(self):
        self.service = InitialisationService()

    def test_charger_plan_comptable(self):
        result = self.service.charger_plan_comptable(entreprise_id="TEST")
        self.assertTrue(result.get("success"))
        self.assertGreater(CompteComptable.objects.count(), 0)

    def test_charger_plan_comptable_ecraser(self):
        CompteComptable.objects.create(code="571", libelle="Old", nature="DEBIT", entreprise_id="TEST")
        self.assertEqual(CompteComptable.objects.count(), 1)
        result = self.service.charger_plan_comptable(force=True, entreprise_id="TEST")
        self.assertTrue(result.get("success"))
        self.assertGreater(CompteComptable.objects.count(), 50)
        compte = CompteComptable.objects.get(code="571")
        self.assertEqual(compte.libelle, "Caisse")

    def test_chart_load_is_bounded_and_preserves_other_tenant(self):
        other = CompteComptable.objects.create(code='571', libelle='Private chart', entreprise_id='OTHER')
        with CaptureQueriesContext(connection) as queries:
            result = self.service.charger_plan_comptable(entreprise_id='BATCH')
        self.assertTrue(result['success'])
        self.assertLess(len(queries), 35, 'Chart initialization must not issue one query per account')
        other.refresh_from_db()
        self.assertEqual(other.libelle, 'Private chart')
        self.assertFalse(CompteComptable.objects.filter(entreprise_id='BATCH').exclude(parent=None).exclude(parent__entreprise_id='BATCH').exists())
        repeated = self.service.charger_plan_comptable(entreprise_id='BATCH')
        self.assertEqual(repeated['comptes_crees'], 0)
        self.assertEqual(CompteComptable.objects.filter(entreprise_id='BATCH').count(), result['total'])

