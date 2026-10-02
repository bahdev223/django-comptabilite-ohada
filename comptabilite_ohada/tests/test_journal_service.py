from django.test import TestCase
from django.contrib.auth.models import User

from ..models import (
    CompteComptable, JournalComptable, ExerciceComptable,
    EcritureComptable, LigneEcritureComptable,
)
from ..services.journal_service import BalanceService
from ..services.ecriture_service import EcritureService


class BalanceServiceTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="compta", password="test1234")
        self.journal = JournalComptable.objects.create(
            code="VN", libelle="Ventes", type_journal="VN"
        )
        self.exercice = ExerciceComptable.objects.create(
            code="2025",
            date_debut="2025-01-01", date_fin="2025-12-31",
        )
        self.compte_caisse = CompteComptable.objects.create(
            code="571", libelle="Caisse", nature="DEBIT", type_compte="compte",
        )
        self.compte_produit = CompteComptable.objects.create(
            code="701", libelle="Ventes", nature="CREDIT", type_compte="compte",
        )
        self.compte_charge = CompteComptable.objects.create(
            code="601", libelle="Achats", nature="DEBIT", type_compte="compte",
        )

    def test_balance_vide(self):
        service = BalanceService()
        balance = service.balance(exercice=self.exercice)
        self.assertEqual(len(balance), 0)

    def test_balance_apres_ecritures(self):
        EcritureService.creer_ecriture(
            journal=self.journal,
            exercice=self.exercice,
            date_ecriture="2025-06-01",
            reference="VN-001",
            libelle="Vente",
            user=self.user,
            lignes=[
                {"compte": self.compte_caisse, "debit": 100000},
                {"compte": self.compte_produit, "credit": 100000},
            ],
        )

        service = BalanceService()
        balance = service.balance(exercice=self.exercice)
        self.assertGreaterEqual(len(balance), 2)
