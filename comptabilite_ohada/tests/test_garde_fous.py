# -*- coding: utf-8 -*-
"""Garde-fous de creer_ecriture.

Deux fonctions du service rendent None plutot que de lever : get_exercice
quand aucun exercice ouvert ne couvre la date, et get_compte quand le
code n'existe pas au plan. L'ecriture partait alors avec une cle nulle et
l'echec remontait en IntegrityError depuis la base -- bien apres le point
ou l'on aurait pu expliquer le probleme, et potentiellement apres qu'une
operation de tresorerie ait deja ete enregistree.

Ces tests fixent le comportement attendu : une erreur metier explicite,
et aucune ecriture creee.
"""

import datetime as dt
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from ..models import (
    CompteComptable,
    EcritureComptable,
    ExerciceComptable,
    JournalComptable,
)
from ..services.ecriture_service import EcritureService


class GardeFousEcritureTest(TestCase):
    def setUp(self):
        self.journal = JournalComptable.objects.create(
            code="CA", libelle="Caisse", type_journal="CAISSE"
        )
        self.compte = CompteComptable.objects.create(
            code="571", libelle="Caisse", niveau=3
        )
        self.autre = CompteComptable.objects.create(
            code="706", libelle="Services vendus", niveau=3
        )

    # Sentinelle : il faut distinguer « non fourni » de « fourni a None »,
    # sinon le helper substitue un compte valide et le test ne teste rien.
    _DEFAUT = object()

    def _lignes(self, compte_debit=_DEFAUT, compte_credit=_DEFAUT):
        return [
            {"compte": self.compte if compte_debit is self._DEFAUT else compte_debit,
             "debit": Decimal("1000"), "credit": Decimal("0")},
            {"compte": self.autre if compte_credit is self._DEFAUT else compte_credit,
             "debit": Decimal("0"), "credit": Decimal("1000")},
        ]

    def test_sans_exercice_ouvert_l_ecriture_est_refusee(self):
        self.assertFalse(ExerciceComptable.objects.exists())
        with self.assertRaises(ValidationError) as ctx:
            EcritureService.creer_ecriture(
                reference="TEST-1", date_ecriture=dt.date(2026, 6, 1),
                libelle="Encaissement", journal=self.journal, lignes=self._lignes(),
            )
        self.assertIn("exercice", str(ctx.exception).lower())
        self.assertEqual(EcritureComptable.objects.count(), 0)

    def test_compte_introuvable_l_ecriture_est_refusee(self):
        ExerciceComptable.objects.create(
            code="2026", date_debut=dt.date(2026, 1, 1),
            date_fin=dt.date(2026, 12, 31), cloture=False,
        )
        # get_compte rend None pour un code absent du plan : c'est ce None
        # qui arrivait jusqu'a la contrainte de base.
        introuvable = EcritureService.get_compte("9999")
        self.assertIsNone(introuvable)

        with self.assertRaises(ValidationError) as ctx:
            EcritureService.creer_ecriture(
                reference="TEST-2", date_ecriture=dt.date(2026, 6, 1),
                libelle="Encaissement", journal=self.journal,
                lignes=self._lignes(compte_debit=introuvable),
            )
        self.assertIn("compte", str(ctx.exception).lower())
        self.assertEqual(EcritureComptable.objects.count(), 0)

    def test_une_ecriture_correcte_passe_toujours(self):
        """Le garde-fou ne doit pas gener le cas nominal."""
        ExerciceComptable.objects.create(
            code="2026", date_debut=dt.date(2026, 1, 1),
            date_fin=dt.date(2026, 12, 31), cloture=False,
        )
        ecriture = EcritureService.creer_ecriture(
            reference="TEST-3", date_ecriture=dt.date(2026, 6, 1),
            libelle="Encaissement", journal=self.journal, lignes=self._lignes(),
        )
        self.assertEqual(EcritureComptable.objects.count(), 1)
        self.assertEqual(ecriture.lignes.count(), 2)
