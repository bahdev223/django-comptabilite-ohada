from django.test import TestCase

from ..models import (
    CompteComptable,
)
from ..services.initialisation_service import InitialisationService


class InitialisationServiceTest(TestCase):
    def setUp(self):
        self.service = InitialisationService()

    def test_charger_plan_comptable(self):
        result = self.service.charger_plan_comptable()
        self.assertTrue(result.get("success"))
        self.assertGreater(CompteComptable.objects.count(), 0)

    def test_charger_plan_comptable_ecraser(self):
        CompteComptable.objects.create(code="571", libelle="Old", nature="DEBIT")
        self.assertEqual(CompteComptable.objects.count(), 1)
        result = self.service.charger_plan_comptable(force=True)
        self.assertTrue(result.get("success"))
        self.assertGreater(CompteComptable.objects.count(), 50)
        compte = CompteComptable.objects.get(code="571")
        self.assertEqual(compte.libelle, "Caisse")
