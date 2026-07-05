from django.test import TestCase
from django.contrib.auth.models import User

from ..models import (
    CompteComptable, JournalComptable, ExerciceComptable,
    EcritureComptable, LigneEcritureComptable,
)
from ..services.ecriture_service import EcritureService


class EcritureServiceTest(TestCase):
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

    def test_creer_ecriture_vente(self):
        ecriture = EcritureService.creer_ecriture_vente(
            compte_caisse_code="571",
            montant=100000,
            libelle="Vente test",
            compte_produit_code="701",
            user=self.user,
        )
        self.assertIsNotNone(ecriture)
        self.assertTrue(ecriture.validee)
        self.assertEqual(ecriture.lignes.count(), 2)
        self.assertEqual(ecriture.lignes.filter(debit=100000).count(), 1)
        self.assertEqual(ecriture.lignes.filter(credit=100000).count(), 1)

    def test_valider_ecriture(self):
        ecriture = EcritureComptable.objects.create(
            journal=self.journal, exercice=self.exercice,
            date_ecriture="2025-06-01", reference="VN-001",
            libelle="Vente test", validee=False, created_by=self.user,
        )
        LigneEcritureComptable.objects.create(
            ecriture=ecriture, compte=self.compte_caisse, debit=50000,
        )
        LigneEcritureComptable.objects.create(
            ecriture=ecriture, compte=self.compte_produit, credit=50000,
        )
        self.assertFalse(ecriture.validee)
        ecriture.validee = True
        ecriture.save()
        ecriture.refresh_from_db()
        self.assertTrue(ecriture.validee)
