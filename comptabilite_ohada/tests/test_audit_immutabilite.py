from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from comptabilite_ohada.models import (
    CompteComptable,
    EcritureComptable,
    ExerciceComptable,
    JournalComptable,
)
from comptabilite_ohada.services.ecriture_service import EcritureService
from comptabilite_ohada.services.exercice_service import ExerciceService, ValidationService


class AuditImmutabiliteTest(TestCase):
    def setUp(self):
        self.exercice = ExerciceComptable.objects.create(
            code="2026",
            date_debut="2026-01-01",
            date_fin="2026-12-31",
        )
        self.journal = JournalComptable.objects.create(
            code="OD",
            libelle="OD",
            type_journal="OD",
        )
        self.debit = CompteComptable.objects.create(
            code="571",
            libelle="Caisse",
            nature="ACTIF",
            sens="DEBIT",
        )
        self.credit = CompteComptable.objects.create(
            code="701",
            libelle="Produit",
            nature="PRODUIT",
            sens="CREDIT",
            categorie="resultat",
        )

    def _ecriture(self, reference="AUD-001", validee=True):
        return EcritureService.creer_ecriture(
            reference=reference,
            date_ecriture="2026-06-01",
            libelle="Audit",
            journal=self.journal,
            exercice=self.exercice,
            validee=validee,
            lignes=[
                {"compte": self.debit, "debit": Decimal("1000")},
                {"compte": self.credit, "credit": Decimal("1000")},
            ],
        )

    def test_ecriture_validee_ne_peut_pas_etre_modifiee(self):
        ecriture = self._ecriture()
        ecriture.libelle = "Modification interdite"
        with self.assertRaises(ValidationError):
            ecriture.save()

    def test_ecriture_validee_ne_peut_pas_etre_supprimee(self):
        ecriture = self._ecriture()
        with self.assertRaises(ValidationError):
            ecriture.delete()
        with self.assertRaises(ValidationError):
            EcritureComptable.objects.filter(pk=ecriture.pk).delete()

    def test_compte_utilise_est_protege(self):
        self._ecriture()
        with self.assertRaises(ProtectedError):
            self.debit.delete()

    def test_annulation_est_idempotente(self):
        ecriture = self._ecriture()
        annulation1 = ValidationService.annuler_ecriture(ecriture, raison="Erreur")
        annulation2 = ValidationService.annuler_ecriture(ecriture, raison="Retry")
        self.assertEqual(annulation1.pk, annulation2.pk)
        self.assertEqual(ecriture.reversals.count(), 1)


class ReouvertureExerciceTest(TestCase):
    def setUp(self):
        self.exercice = ExerciceComptable.objects.create(
            code="2026",
            date_debut="2026-01-01",
            date_fin="2026-12-31",
        )
        self.journal = JournalComptable.objects.create(
            code="OD",
            libelle="OD",
            type_journal="OD",
        )
        self.charge = CompteComptable.objects.create(
            code="601",
            libelle="Charge",
            nature="CHARGE",
            sens="DEBIT",
            categorie="resultat",
        )
        self.caisse = CompteComptable.objects.create(
            code="571",
            libelle="Caisse",
            nature="ACTIF",
            sens="CREDIT",
        )
        self.resultat = CompteComptable.objects.create(
            code="129",
            libelle="Résultat",
            nature="PASSIF",
            sens="DEBIT",
        )
        self.capital = CompteComptable.objects.create(
            code="101",
            libelle="Capital",
            nature="PASSIF",
            sens="CREDIT",
        )
        EcritureService.creer_ecriture(
            reference="CHARGE-1",
            date_ecriture="2026-06-01",
            libelle="Charge",
            journal=self.journal,
            exercice=self.exercice,
            lignes=[
                {"compte": self.charge, "debit": Decimal("1000")},
                {"compte": self.caisse, "credit": Decimal("1000")},
            ],
        )

    def test_reouverture_contre_passe_cloture_et_permet_recloture(self):
        ExerciceService.cloturer(self.exercice)
        self.exercice.refresh_from_db()
        self.assertTrue(self.exercice.cloture)

        cloture = EcritureComptable.objects.filter(
            source_type="fiscal_closure",
            source_id=str(self.exercice.pk),
        ).latest("created_at")

        ExerciceService.rouvrir(self.exercice)
        self.exercice.refresh_from_db()
        self.assertFalse(self.exercice.cloture)
        self.assertEqual(cloture.reversals.count(), 1)

        ExerciceService.cloturer(self.exercice)
        self.exercice.refresh_from_db()
        self.assertTrue(self.exercice.cloture)
        self.assertEqual(
            EcritureComptable.objects.filter(
                source_type="fiscal_closure",
                source_id=str(self.exercice.pk),
            ).count(),
            2,
        )
