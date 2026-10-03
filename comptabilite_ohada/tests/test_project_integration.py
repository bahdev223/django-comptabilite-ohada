from copy import deepcopy

from django.test import TestCase, override_settings

from comptabilite_ohada.models import (
    CompteComptable,
    EcritureComptable,
    ExerciceComptable,
    JournalComptable,
)


@override_settings(
    ROOT_URLCONF="comptabilite_ohada.integration_urls",
    COMPTABILITE_OHADA={
        "API_ENABLED": True,
        "COMPTES_INTEGRATION_ENABLED": False,
        "DEVISE_PAR_DEFAUT": "XOF",
        "INTEGRATION_KEYS": {"ALPHA": "alpha-test-key", "BETA": "beta-test-key"},
    }
)
class ProjectIntegrationTests(TestCase):
    def setUp(self):
        for tenant in ("ALPHA", "BETA"):
            ExerciceComptable.objects.create(
                entreprise_id=tenant,
                code="2026",
                date_debut="2026-01-01",
                date_fin="2026-12-31",
            )
            JournalComptable.objects.create(
                entreprise_id=tenant,
                code="OD",
                libelle="Opérations diverses",
                type_journal="OD",
            )
            CompteComptable.objects.create(
                entreprise_id=tenant,
                code="658",
                libelle="Autres charges",
                nature="CHARGE",
                sens="DEBIT",
            )
            CompteComptable.objects.create(
                entreprise_id=tenant,
                code="571",
                libelle="Caisse",
                nature="ACTIF",
                sens="DEBIT",
            )

    @staticmethod
    def event(key, amount, project="SAME"):
        return {
            "type_evenement": "project.expense.created",
            "source_system": "saheltech-platform",
            "source_type": "project",
            "source_id": key,
            "idempotency_key": key,
            "payload": {
                "date": "2026-10-03",
                "libelle": "Dépense projet",
                "journal_code": "OD",
                "source_reference": project,
                "dimensions": {"PROJECT": project},
                "lignes": [
                    {"compte": "658", "debit": amount, "dimensions": {"PROJECT": project}},
                    {"compte": "571", "credit": amount, "dimensions": {"PROJECT": project}},
                ],
            },
        }

    def post_event(self, tenant, payload):
        key = "alpha-test-key" if tenant == "ALPHA" else "beta-test-key"
        return self.client.post(
            "/api/v1/events/", payload, content_type="application/json", HTTP_X_API_KEY=key
        )

    def costs(self, tenant, project="SAME", **dimensions):
        key = "alpha-test-key" if tenant == "ALPHA" else "beta-test-key"
        return self.client.get(
            "/api/v1/analytics/costs/",
            {"PROJECT": project, **dimensions},
            HTTP_X_API_KEY=key,
        )

    def test_same_project_code_has_separate_validated_costs_per_tenant(self):
        self.assertEqual(self.post_event("ALPHA", self.event("A-1", "125.00")).status_code, 201)
        self.assertEqual(self.post_event("BETA", self.event("B-1", "80.00")).status_code, 201)

        self.assertEqual(self.costs("ALPHA").json()["total_cost"], "125.00")
        self.assertEqual(self.costs("ALPHA").json()["currency"], "XOF")
        self.assertEqual(self.costs("BETA").json()["total_cost"], "80.00")
        self.assertEqual(self.costs("ALPHA", "ABSENT").json()["total_cost"], "0.00")
        self.assertEqual(EcritureComptable.objects.filter(entreprise_id="ALPHA").count(), 1)
        self.assertEqual(EcritureComptable.objects.filter(entreprise_id="BETA").count(), 1)

    def test_event_replay_is_idempotent_and_changed_payload_conflicts(self):
        event = self.event("A-2", "40.00")
        first = self.post_event("ALPHA", event)
        self.assertEqual(first.status_code, 201)
        replay = self.post_event("ALPHA", event)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json()["entry_id"], first.json()["entry_id"])

        changed = deepcopy(event)
        changed["payload"]["libelle"] = "Autre dépense"
        self.assertEqual(self.post_event("ALPHA", changed).status_code, 409)
        self.assertEqual(EcritureComptable.objects.count(), 1)

    def test_replay_remains_idempotent_after_accounting_period_closes(self):
        event = self.event("A-CLOSED", "40.00")
        first = self.post_event("ALPHA", event)
        self.assertEqual(first.status_code, 201)
        ExerciceComptable.objects.filter(entreprise_id="ALPHA").update(cloture=True)
        JournalComptable.objects.filter(entreprise_id="ALPHA").update(actif=False)

        replay = self.post_event("ALPHA", event)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json()["entry_id"], first.json()["entry_id"])
        self.assertEqual(EcritureComptable.objects.count(), 1)

    def test_long_entry_label_fits_the_accounting_line_field(self):
        event = self.event("A-LONG", "40.00")
        event["payload"]["libelle"] = "Travaux " * 40
        response = self.post_event("ALPHA", event)
        self.assertEqual(response.status_code, 201)
        entry = EcritureComptable.objects.get(pk=response.json()["entry_id"])
        self.assertEqual(entry.libelle, event["payload"]["libelle"].strip())
        self.assertTrue(all(len(line.libelle) <= 200 for line in entry.lignes.all()))

    def test_foreign_account_and_forged_project_dimension_are_rejected(self):
        CompteComptable.objects.filter(entreprise_id="ALPHA", code="658").delete()
        self.assertEqual(self.post_event("ALPHA", self.event("A-3", "50.00")).status_code, 400)

        forged = self.event("A-4", "50.00")
        forged["payload"]["lignes"][0]["dimensions"]["PROJECT"] = "OTHER"
        self.assertEqual(self.post_event("ALPHA", forged).status_code, 400)
        self.assertEqual(EcritureComptable.objects.count(), 0)

    def test_missing_or_wrong_key_cannot_read_or_write(self):
        self.assertEqual(self.client.get("/api/v1/analytics/costs/", {"PROJECT": "SAME"}).status_code, 401)
        self.assertEqual(
            self.client.get(
                "/api/v1/analytics/costs/", {"PROJECT": "SAME"}, HTTP_X_API_KEY="wrong"
            ).status_code,
            401,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/events/",
                self.event("A-5", "30.00"),
                content_type="application/json",
                HTTP_X_API_KEY="wrong",
            ).status_code,
            401,
        )
        self.assertEqual(EcritureComptable.objects.count(), 0)

    def test_service_host_does_not_expose_the_legacy_accounting_api(self):
        self.assertEqual(self.client.get("/api/comptabilite/comptes/").status_code, 404)

    def test_costs_use_only_validated_charge_lines_and_exact_dimensions(self):
        phase_one = self.event("A-PH1", "30.00")
        phase_one["payload"]["dimensions"]["PHASE"] = "PH1"
        phase_two = self.event("A-PH2", "20.00")
        phase_two["payload"]["dimensions"]["PHASE"] = "PH2"
        self.assertEqual(self.post_event("ALPHA", phase_one).status_code, 201)
        self.assertEqual(self.post_event("ALPHA", phase_two).status_code, 201)
        self.assertEqual(self.costs("ALPHA", PHASE="PH1").json()["total_cost"], "30.00")
        self.assertEqual(self.costs("ALPHA", PHASE="PH2").json()["total_cost"], "20.00")
        self.assertEqual(self.costs("ALPHA", PHASE="PH").json()["total_cost"], "0.00")

        first = EcritureComptable.objects.filter(entreprise_id="ALPHA").order_by("id").first()
        first.validee = False
        first.save(update_fields=["validee"])
        self.assertEqual(self.costs("ALPHA").json()["total_cost"], "20.00")

        CompteComptable.objects.create(
            entreprise_id="ALPHA",
            code="521",
            libelle="Banque",
            nature="ACTIF",
            sens="DEBIT",
        )
        asset_transfer = self.event("A-ASSET", "100.00")
        asset_transfer["payload"]["lignes"][0]["compte"] = "521"
        self.assertEqual(self.post_event("ALPHA", asset_transfer).status_code, 201)
        self.assertEqual(self.costs("ALPHA").json()["total_cost"], "20.00")
