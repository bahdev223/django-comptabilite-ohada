from django.test import TestCase
from django.contrib.auth.models import User

from ..models import (
    CompteComptable, JournalComptable, ExerciceComptable,
    EcritureComptable, LigneEcritureComptable,
)
from ..services.journal_service import BalanceService


class BalanceServiceTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="compta", password="test1234")
        self.journal = JournalComptable.objects.create(
            code="VN", libelle="Ventes", type_journal="VN"
        )
        self.exercice = ExerciceComptable.objects.create(
            code="2025", libelle="Exercice 2025",
            date_debut="2025-01-01", date_fin="2025-12-31",
        )
        self.compte_caisse = CompteComptable.objects.create(
            code="571", libelle="Caisse", classe=5, nature="DEBIT",
        )
        self.compte_produit = CompteComptable.objects.create(
            code="701", libelle="Ventes", classe=7, nature="CREDIT",
        )
        self.compte_charge = CompteComptable.objects.create(
            code="601", libelle="Achats", classe=6, nature="DEBIT",
        )

    def test_balance_vide(self):
        service = BalanceService()
        balance = service.generer_balance(exercice_id=self.exercice.pk)
        self.assertEqual(len(balance), 0)

    def test_balance_apres_ecritures(self):
        ecriture_v = EcritureComptable.objects.create(
            journal=self.journal, exercice=self.exercice,
            date_ecriture="2025-06-01", reference="VN-001",
            libelle="Vente", type_operation="VENTE",
            validee=True, createur=self.user,
        )
        LigneEcritureComptable.objects.create(
            ecriture=ecriture_v, compte=self.compte_caisse, debit=100000,
        )
        LigneEcritureComptable.objects.create(
            ecriture=ecriture_v, compte=self.compte_produit, credit=100000,
        )

        service = BalanceService()
        balance = service.generer_balance(exercice_id=self.exercice.pk)
        self.assertGreaterEqual(len(balance), 2)

        caisse = next(b for b in balance if b["compte__code"] == "571")
        self.assertEqual(caisse["total_debit"], 100000)
