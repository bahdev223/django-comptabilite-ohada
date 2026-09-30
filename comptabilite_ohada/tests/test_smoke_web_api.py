from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client, TestCase

from comptabilite_ohada.models import (
    ApplicationClienteComptable,
    ExerciceComptable,
    Immobilisation,
    OrganisationComptable,
    ReleveBancaire,
    RegleEvenementComptable,
)
from comptabilite_ohada.services.initialisation_service import InitialisationService
from comptabilite_ohada.services.ecriture_service import EcritureService


class HTMLSmokeTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="admin-smoke",
            email="smoke@example.com",
            password="test-pass",
        )
        self.client.force_login(self.user)
        InitialisationService.charger_plan_comptable(force=True)
        InitialisationService.initialiser_journaux()
        self.exercice = ExerciceComptable.objects.create(
            code="2026",
            date_debut=date(2026, 1, 1),
            date_fin=date(2026, 12, 31),
        )
        self.compte = EcritureService.get_compte("571")
        self.releve = ReleveBancaire.objects.create(
            compte_comptable_code="521",
            date_debut=date(2026, 9, 1),
            date_fin=date(2026, 9, 30),
            solde_ouverture=Decimal("100000"),
            solde_cloture=Decimal("100000"),
        )
        self.immo = Immobilisation.objects.create(
            code="IMMO-SMOKE",
            libelle="Matériel test",
            type_immobilisation="CORPORELLE",
            date_acquisition=date(2026, 1, 1),
            valeur_originale=Decimal("120000"),
            valeur_residuelle=Decimal("0"),
            duree_ans=1,
            compte_immobilisation=EcritureService.get_compte("245"),
            compte_amortissement=EcritureService.get_compte("28"),
            compte_charge=EcritureService.get_compte("68"),
        )

    def test_pages_principales_rendent_sans_erreur(self):
        urls = [
            "/",
            "/ecritures/",
            "/ecritures/creer/",
            "/comptes/",
            f"/comptes/{self.compte.pk}/",
            "/journaux/",
            "/balance/",
            "/grand-livre/",
            "/bilan/",
            "/compte-resultat/",
            "/exercices/",
            f"/exercices/{self.exercice.pk}/",
            "/immobilisations/",
            f"/immobilisations/{self.immo.pk}/",
            "/rapprochement/",
            f"/rapprochement/{self.releve.pk}/",
            "/exports/?type=ecritures",
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(
                    response.status_code,
                    200,
                    msg=f"{url} -> {response.status_code}",
                )


class APIStandaloneSmokeTest(TestCase):
    entreprise = "ENT-API-SMOKE"

    def setUp(self):
        self.org = OrganisationComptable.objects.create(
            code=self.entreprise,
            nom="Entreprise API Smoke",
        )
        self.application, self.secret = ApplicationClienteComptable.generer_cle(
            entreprise=self.org,
            nom="saheltech-platform-smoke",
            scopes=["*"],
        )
        InitialisationService.charger_plan_comptable(
            force=True, entreprise_id=self.entreprise
        )
        InitialisationService.initialiser_journaux(self.entreprise)
        self.exercice = ExerciceComptable.objects.create(
            code="2026",
            date_debut=date(2026, 1, 1),
            date_fin=date(2026, 12, 31),
            entreprise_id=self.entreprise,
        )
        self.client = Client(HTTP_X_API_KEY=self.secret)

    def test_health_et_ressources_principales(self):
        self.assertEqual(
            self.client.get("/api/v1/health/").status_code, 200
        )
        self.assertEqual(
            self.client.get("/api/v1/organisations/").status_code, 200
        )
        self.assertEqual(
            self.client.get("/api/v1/comptes/").status_code, 200
        )
        self.assertEqual(
            self.client.get("/api/v1/ecritures/balance/").status_code, 200
        )
        self.assertEqual(
            self.client.get("/api/v1/ecritures/grand_livre/").status_code, 200
        )
        self.assertEqual(
            self.client.get(
                f"/api/v1/ecritures/bilan/?exercice={self.exercice.pk}"
            ).status_code,
            200,
        )

    def test_evenement_generique_via_api_cree_ecriture(self):
        RegleEvenementComptable.objects.create(
            entreprise_id=self.entreprise,
            type_evenement="project.expense.created",
            code_regle="ECRITURE_GENERIQUE",
        )
        payload = {
            "type_evenement": "project.expense.created",
            "source_system": "saheltech-platform",
            "source_type": "project.expense",
            "source_id": "EXP-SMOKE-1",
            "idempotency_key": "project:expense:EXP-SMOKE-1:v1",
            "payload": {
                "date": "2026-09-30",
                "libelle": "Dépense mission",
                "journal_code": "OD",
                "lignes": [
                    {
                        "compte": "658",
                        "debit": "5000",
                        "dimensions": {
                            "PROJECT": "PROJ-1",
                            "MISSION": "MIS-1",
                        },
                    },
                    {
                        "compte": "552",
                        "credit": "5000",
                        "dimensions": {
                            "PROJECT": "PROJ-1",
                            "MISSION": "MIS-1",
                        },
                    },
                ],
            },
        }
        response = self.client.post(
            "/api/v1/events/",
            data=payload,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertEqual(data["statut"], "TRAITE")
        self.assertIsNotNone(data["ecriture"])

        second = self.client.post(
            "/api/v1/events/",
            data=payload,
            content_type="application/json",
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["ecriture"], data["ecriture"])
