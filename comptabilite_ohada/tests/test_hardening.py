from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from comptabilite_ohada.models import (
    CompteComptable,
    EcritureComptable,
    ExerciceComptable,
    JournalComptable,
)
from comptabilite_ohada.services.ecriture_service import EcritureService
from comptabilite_ohada.services.exercice_service import ExerciceService


class HardeningComptableTest(TestCase):
    def _compte(self, code, entreprise_id, nature="ACTIF", sens="DEBIT"):
        return CompteComptable.objects.create(
            code=code,
            libelle=f"Compte {code}",
            nature=nature,
            sens=sens,
            entreprise_id=entreprise_id,
        )

    def _journal(self, entreprise_id):
        return JournalComptable.objects.create(
            code="OD",
            libelle="Operations diverses",
            type_journal="OD",
            entreprise_id=entreprise_id,
        )

    def _exercice(self, entreprise_id, code="2026"):
        return ExerciceComptable.objects.create(
            code=code,
            date_debut="2026-01-01",
            date_fin="2026-12-31",
            entreprise_id=entreprise_id,
        )

    def test_get_exercice_ne_prend_pas_un_exercice_hors_periode(self):
        self._exercice("", code="2025")
        exercice = ExerciceComptable.objects.get(code="2025")
        exercice.date_debut = "2025-01-01"
        exercice.date_fin = "2025-12-31"
        exercice.save(update_fields=["date_debut", "date_fin"])

        self.assertIsNone(EcritureService.get_exercice("2026-02-10"))

    def test_ecriture_est_scopee_par_entreprise(self):
        exercice_a = self._exercice("A")
        journal_a = self._journal("A")
        caisse_a = self._compte("571", "A")
        produit_a = self._compte("701", "A", nature="PRODUIT", sens="CREDIT")

        ecriture = EcritureService.creer_ecriture(
            reference="A-001",
            date_ecriture="2026-06-01",
            libelle="Vente A",
            journal=journal_a,
            exercice=exercice_a,
            entreprise_id="A",
            lignes=[
                {"compte": caisse_a, "debit": Decimal("1000")},
                {"compte": produit_a, "credit": Decimal("1000")},
            ],
        )

        self.assertEqual(ecriture.entreprise_id, "A")

    def test_compte_d_une_autre_entreprise_est_refuse(self):
        exercice_a = self._exercice("A")
        journal_a = self._journal("A")
        caisse_a = self._compte("571", "A")
        produit_b = self._compte("701", "B", nature="PRODUIT", sens="CREDIT")

        with self.assertRaises(ValidationError):
            EcritureService.creer_ecriture(
                reference="A-002",
                date_ecriture="2026-06-01",
                libelle="Melange interdit",
                journal=journal_a,
                exercice=exercice_a,
                entreprise_id="A",
                lignes=[
                    {"compte": caisse_a, "debit": Decimal("1000")},
                    {"compte": produit_b, "credit": Decimal("1000")},
                ],
            )

        self.assertFalse(EcritureComptable.objects.filter(reference="A-002").exists())

    def test_cloture_resultat_nul_ne_cree_pas_ecriture_zero(self):
        exercice = self._exercice("")
        ExerciceService.cloturer(exercice)
        exercice.refresh_from_db()

        self.assertTrue(exercice.cloture)
        self.assertFalse(EcritureComptable.objects.filter(reference__startswith="RES-").exists())
