from decimal import Decimal

from django.test import TestCase

from comptabilite_ohada.models import (
    AffectationAnalytique,
    CompteComptable,
    DimensionAnalytique,
    EcritureComptable,
    ExerciceComptable,
    RegleEvenementComptable,
)
from comptabilite_ohada.services.evenement_service import EvenementService


class EvenementIntegrationTest(TestCase):
    def setUp(self):
        self.entreprise_id = "SOLARPLUS"
        ExerciceComptable.objects.create(
            code="2026",
            date_debut="2026-01-01",
            date_fin="2026-12-31",
            entreprise_id=self.entreprise_id,
        )
        CompteComptable.objects.create(
            code="571",
            libelle="Caisse",
            nature="ACTIF",
            sens="DEBIT",
            entreprise_id=self.entreprise_id,
        )
        CompteComptable.objects.create(
            code="701",
            libelle="Ventes",
            nature="PRODUIT",
            sens="CREDIT",
            categorie="resultat",
            entreprise_id=self.entreprise_id,
        )
        RegleEvenementComptable.objects.create(
            entreprise_id=self.entreprise_id,
            type_evenement="sale.completed",
            code_regle="VENTE_COMPTANT",
        )

    def test_evenement_idempotent_cree_une_seule_ecriture(self):
        kwargs = {
            "entreprise_id": self.entreprise_id,
            "type_evenement": "sale.completed",
            "source_system": "saheltech-platform",
            "source_type": "sale",
            "source_id": "SALE-001",
            "idempotency_key": "sale:SALE-001:v1",
            "payload": {
                "montant": Decimal("100000"),
                "date": __import__("datetime").date(2026, 6, 1),
                "libelle": "Vente test",
                "compte_caisse": "571",
                "compte_produit": "701",
                "dimensions": {
                    "PROJECT": "PROJ-19",
                    "PHASE": "INSTALLATION",
                },
            },
        }

        evenement1, created1 = EvenementService.recevoir(**kwargs)
        evenement2, created2 = EvenementService.recevoir(**kwargs)

        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(evenement1.pk, evenement2.pk)
        self.assertEqual(EcritureComptable.objects.count(), 1)
        self.assertEqual(evenement1.statut, "TRAITE")
        self.assertEqual(evenement1.ecriture.source_system, "saheltech-platform")
        self.assertEqual(evenement1.ecriture.source_id, "SALE-001")

    def test_dimensions_analytiques_sont_abstraites_du_metier(self):
        evenement, _ = EvenementService.recevoir(
            entreprise_id=self.entreprise_id,
            type_evenement="sale.completed",
            source_system="solarplus",
            source_type="project.sale",
            source_id="SALE-002",
            idempotency_key="sale:SALE-002:v1",
            payload={
                "montant": Decimal("50000"),
                "date": __import__("datetime").date(2026, 6, 2),
                "libelle": "Opération projet",
                "compte_caisse": "571",
                "compte_produit": "701",
                "dimensions": {
                    "PROJECT": {"code": "PROJ-20", "libelle": "Projet Sikasso"},
                    "MISSION": "MIS-44",
                },
            },
        )

        self.assertEqual(evenement.statut, "TRAITE")
        self.assertTrue(
            DimensionAnalytique.objects.filter(
                entreprise_id=self.entreprise_id, code="PROJECT"
            ).exists()
        )
        self.assertTrue(
            DimensionAnalytique.objects.filter(
                entreprise_id=self.entreprise_id, code="MISSION"
            ).exists()
        )
        # Deux lignes x deux axes analytiques.
        self.assertEqual(
            AffectationAnalytique.objects.filter(
                ligne__ecriture=evenement.ecriture
            ).count(),
            4,
        )

    def test_evenement_sans_mapping_est_ignore_sans_ecriture(self):
        evenement, created = EvenementService.recevoir(
            entreprise_id=self.entreprise_id,
            type_evenement="btp.unknown",
            source_system="btp",
            source_id="X-1",
            idempotency_key="btp:X-1:v1",
            payload={"montant": 1000},
        )

        self.assertTrue(created)
        self.assertEqual(evenement.statut, "IGNORE")
        self.assertIsNone(evenement.ecriture)
