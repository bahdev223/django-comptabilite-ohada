from django.test import TestCase
from django.contrib.auth.models import User

from ..models import (
    CompteComptable, JournalComptable, ExerciceComptable,
    EcritureComptable, LigneEcritureComptable,
)


class CompteComptableModelTest(TestCase):
    def setUp(self):
        self.compte = CompteComptable.objects.create(
            code="571",
            libelle="Caisse",
            nature="DEBIT",
            type_compte="compte",
        )

    def test_compte_str(self):
        self.assertEqual(str(self.compte), "571 - Caisse")

    def test_compte_actif_par_defaut(self):
        self.assertTrue(self.compte.actif)

    def test_compte_calculer_solde_vide(self):
        solde = self.compte.calculer_solde()
        self.assertEqual(solde, 0)


class EcritureComptableModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="compta", password="test1234")
        self.journal = JournalComptable.objects.create(
            code="VN", libelle="Journal des ventes", type_journal="VN"
        )
        self.exercice = ExerciceComptable.objects.create(
            code="2025",
            date_debut="2025-01-01", date_fin="2025-12-31",
        )
        self.compte_571 = CompteComptable.objects.create(
            code="571", libelle="Caisse", nature="DEBIT", type_compte="compte",
        )
        self.compte_701 = CompteComptable.objects.create(
            code="701", libelle="Ventes", nature="CREDIT", type_compte="compte",
        )

    def test_ecriture_equilibree(self):
        ecriture = EcritureComptable.objects.create(
            journal=self.journal,
            exercice=self.exercice,
            date_ecriture="2025-06-01",
            reference="VN-001",
            libelle="Vente comptant",
            created_by=self.user,
        )
        LigneEcritureComptable.objects.create(
            ecriture=ecriture, compte=self.compte_571, debit=100000,
        )
        LigneEcritureComptable.objects.create(
            ecriture=ecriture, compte=self.compte_701, credit=100000,
        )

        total_debit = sum(l.debit for l in ecriture.lignes.all())
        total_credit = sum(l.credit for l in ecriture.lignes.all())
        self.assertEqual(total_debit, total_credit)

    def test_ecriture_desequilibree(self):
        ecriture = EcritureComptable.objects.create(
            journal=self.journal,
            exercice=self.exercice,
            date_ecriture="2025-06-01",
            reference="VN-002",
            libelle="Vente déséquilibrée",
            created_by=self.user,
        )
        LigneEcritureComptable.objects.create(
            ecriture=ecriture, compte=self.compte_571, debit=100000,
        )
        total_debit = sum(l.debit for l in ecriture.lignes.all())
        total_credit = sum(l.credit for l in ecriture.lignes.all())
        self.assertNotEqual(total_debit, total_credit)


class ExerciceComptableModelTest(TestCase):
    def test_exercice_ouvert_par_defaut(self):
        exercice = ExerciceComptable.objects.create(
            code="2025",
            date_debut="2025-01-01", date_fin="2025-12-31",
        )
        self.assertFalse(exercice.cloture)

    def test_exercice_str(self):
        exercice = ExerciceComptable.objects.create(
            code="2025",
            date_debut="2025-01-01", date_fin="2025-12-31",
        )
        self.assertIn("2025", str(exercice))
