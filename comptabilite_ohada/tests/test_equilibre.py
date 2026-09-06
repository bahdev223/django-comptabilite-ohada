"""
La regle fondatrice : une ecriture desequilibree ne doit JAMAIS etre validee.

Ce paquet l'a deja laissee passer par le passe. On ne verifie donc pas que le
code contient un `if` : on essaie de faire entrer une ecriture fausse par
CHAQUE porte, et l'on regarde si l'une d'elles cede.
"""
from decimal import Decimal

from django.test import TestCase

from comptabilite_ohada.models import (
    CompteComptable, EcritureComptable, ExerciceComptable, JournalComptable,
    LigneEcritureComptable,
)
from comptabilite_ohada.services.ecriture_service import EcritureService
from comptabilite_ohada.services.exercice_service import ValidationService


class UneEcritureFausseNePasseParAucunePorte(TestCase):
    def setUp(self):
        self.exercice = ExerciceComptable.objects.create(
            code="2026", date_debut="2026-01-01", date_fin="2026-12-31",
        )
        self.journal = JournalComptable.objects.create(
            code="VT", libelle="Ventes", type_journal="VENTES",
        )
        # 571 Caisse : un compte d'actif, qui augmente au DEBIT.
        self.caisse = CompteComptable.objects.create(
            code="571000", libelle="Caisse", nature="ACTIF", sens="DEBIT",
        )
        # 701 Ventes : un compte de produit, qui augmente au CREDIT.
        self.vente = CompteComptable.objects.create(
            code="701000", libelle="Ventes de marchandises",
            nature="PRODUIT", sens="CREDIT",
        )

    def _lignes_fausses(self):
        """100 000 au debit, 90 000 au credit : 10 000 sortis de nulle part."""
        return [
            {"compte": self.caisse, "debit": Decimal("100000")},
            {"compte": self.vente, "credit": Decimal("90000")},
        ]

    def test_le_service_refuse_de_la_creer(self):
        with self.assertRaises(Exception) as capture:
            EcritureService.creer_ecriture(
                journal=self.journal, exercice=self.exercice,
                date_ecriture="2026-06-01", reference="FAUSSE-1",
                libelle="Tentative", lignes=self._lignes_fausses(),
            )
        self.assertIn("desequilibree", str(capture.exception).lower().replace("é", "e"))

    def test_creee_a_la_main_elle_ne_peut_pas_etre_validee(self):
        """
        On contourne le service et l'on ecrit directement en base — ce que
        ferait un import, un script de reprise, ou du code ecrit vite. La
        SECONDE porte doit tenir.
        """
        ecriture = EcritureComptable.objects.create(
            journal=self.journal, exercice=self.exercice,
            date_ecriture="2026-06-01", reference="FAUSSE-2",
            libelle="Tentative", validee=False,
        )
        for ligne in self._lignes_fausses():
            LigneEcritureComptable.objects.create(ecriture=ecriture, **ligne)

        self.assertFalse(ecriture.est_equilibree)
        with self.assertRaises(ValueError):
            ValidationService.valider_ecriture(ecriture)

        ecriture.refresh_from_db()
        self.assertFalse(ecriture.validee, "une ecriture fausse a ete validee")

    def test_une_ecriture_juste_passe(self):
        """
        Le garde-fou ne doit pas bloquer le travail normal.

        A noter : `creer_ecriture` valide par DEFAUT (`validee=True`). Une
        ecriture nait donc posee au grand livre, pas en brouillon. C'est un
        choix du paquet, et il faut le connaitre avant de brancher quoi que
        ce soit dessus : une vente enregistree par erreur ne s'efface plus,
        elle se contre-passe.
        """
        ecriture = EcritureService.creer_ecriture(
            validee=False,
            journal=self.journal, exercice=self.exercice,
            date_ecriture="2026-06-01", reference="JUSTE-1",
            libelle="Vente du jour",
            lignes=[
                {"compte": self.caisse, "debit": Decimal("100000")},
                {"compte": self.vente, "credit": Decimal("100000")},
            ],
        )
        self.assertTrue(ecriture.est_equilibree)
        ValidationService.valider_ecriture(ecriture)
        ecriture.refresh_from_db()
        self.assertTrue(ecriture.validee)

    def test_le_solde_du_compte_suit_les_ecritures_validees(self):
        from comptabilite_ohada.services.journal_service import BalanceService

        EcritureService.creer_ecriture(
            journal=self.journal, exercice=self.exercice,
            date_ecriture="2026-06-01", reference="JUSTE-2",
            libelle="Vente", validee=True,
            lignes=[
                {"compte": self.caisse, "debit": Decimal("50000")},
                {"compte": self.vente, "credit": Decimal("50000")},
            ],
        )
        self.assertEqual(BalanceService.solde_compte(self.caisse), Decimal("50000"))
