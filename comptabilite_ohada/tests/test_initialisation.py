from django.test import TestCase
from django.contrib.auth.models import User

from ..models import (
    CompteComptable, JournalComptable, ExerciceComptable,
)
from ..services.initialisation_service import InitialisationService


class InitialisationServiceTest(TestCase):
    def setUp(self):
        self.service = InitialisationService()
        self.donnees = [
            {"code": "101", "libelle": "Capital", "classe": 1, "nature": "CREDIT"},
            {"code": "571", "libelle": "Caisse", "classe": 5, "nature": "DEBIT"},
            {"code": "701", "libelle": "Ventes", "classe": 7, "nature": "CREDIT"},
        ]

    def test_charger_plan_comptable(self):
        comptes = self.service.charger_plan_comptable(self.donnees)
        self.assertEqual(len(comptes), 3)
        self.assertEqual(CompteComptable.objects.count(), 3)

    def test_charger_plan_comptable_ecraser(self):
        CompteComptable.objects.create(code="571", libelle="Old", classe=5, nature="DEBIT")
        comptes = self.service.charger_plan_comptable(self.donnees, ecraser=True)
        compte = CompteComptable.objects.get(code="571")
        self.assertEqual(compte.libelle, "Caisse")
