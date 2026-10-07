"""The PR #2 HTTP journey exercised against the single PR #1 accounting core."""

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch

from django.db import close_old_connections, connections
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient

from comptabilite_ohada.models import (
    AffectationAnalytique, ApplicationClienteComptable, CompteComptable,
    ConfigurationComptable, EcritureComptable, EvenementMetier,
    ExerciceComptable, JournalComptable, OrganisationComptable,
    RegleEvenementComptable,
)
from comptabilite_ohada.services.ecriture_service import EcritureService
from comptabilite_ohada.services.exercice_service import ValidationService


@override_settings(COMPTABILITE_OHADA={
    "API_ENABLED": True, "COMPTES_INTEGRATION_ENABLED": False,
    "REQUIRE_TENANT_MEMBERSHIP": True, "DEVISE_PAR_DEFAUT": "XOF",
})
class ProjectIntegrationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.keys = {}
        self.apps = {}
        for tenant in ("ALPHA", "BETA"):
            organisation = OrganisationComptable.objects.create(code=tenant, nom=tenant)
            self.apps[tenant], self.keys[tenant] = ApplicationClienteComptable.generer_cle(
                organisation, "project-client", ["accounting.events.write", "accounting.read"]
            )
            ConfigurationComptable.objects.create(entreprise_id=tenant, devise="XOF")
            ExerciceComptable.objects.create(
                entreprise_id=tenant, code="2026",
                date_debut="2026-01-01", date_fin="2026-12-31",
            )
            JournalComptable.objects.create(
                entreprise_id=tenant, code="OD", libelle="Opérations diverses", type_journal="OD",
            )
            for code, nature in (("658", "CHARGE"), ("571", "ACTIF"), ("521", "ACTIF")):
                CompteComptable.objects.create(
                    entreprise_id=tenant, code=code, libelle=code, nature=nature, sens="DEBIT",
                )
            RegleEvenementComptable.objects.create(
                entreprise_id=tenant, type_evenement="project.expense.created",
                code_regle="ECRITURE_GENERIQUE",
            )

    @staticmethod
    def event(key, amount="40.00", project="SAME"):
        return {
            "type_evenement": "project.expense.created", "source_system": "saheltech-platform",
            "source_type": "project", "source_id": key, "idempotency_key": key,
            "payload": {
                "date": "2026-10-03", "libelle": "Dépense projet", "journal_code": "OD",
                "source_reference": project, "dimensions": {"PROJECT": project},
                "lignes": [
                    {"compte": "658", "debit": amount, "dimensions": {"PROJECT": project}},
                    {"compte": "571", "credit": amount, "dimensions": {"PROJECT": project}},
                ],
            },
        }

    def post_event(self, tenant, payload, **headers):
        return self.client.post(
            "/api/v1/events/", payload, format="json", HTTP_X_API_KEY=self.keys[tenant], **headers,
        )

    def costs(self, tenant="ALPHA", project="SAME", **dimensions):
        return self.client.get(
            "/api/v1/analytics/costs/", {"PROJECT": project, **dimensions},
            HTTP_X_API_KEY=self.keys[tenant],
        )

    def test_project_http_costs_are_tenant_scoped(self):
        self.assertEqual(self.post_event("ALPHA", self.event("SAME-KEY", "125.00")).status_code, 201)
        self.assertEqual(self.post_event("BETA", self.event("SAME-KEY", "80.00")).status_code, 201)
        self.assertEqual(self.costs().json()["total_cost"], "125.00")
        self.assertEqual(self.costs().json()["currency"], "XOF")
        self.assertEqual(self.costs("BETA").json()["total_cost"], "80.00")
        self.assertEqual(self.costs(project="ABSENT").json()["total_cost"], "0.00")
        self.assertEqual(EvenementMetier.objects.count(), 2)
        self.assertEqual(EcritureComptable.objects.count(), 2)

    def test_same_event_replay_returns_the_same_entry(self):
        event = self.event("REPLAY")
        first = self.post_event("ALPHA", event)
        replay = self.post_event("ALPHA", event)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json()["entry_id"], first.json()["entry_id"])
        self.assertEqual(replay.json()["status"], "recorded")
        self.assertEqual(EcritureComptable.objects.count(), 1)

    def test_changed_payload_or_source_conflicts_without_mutation(self):
        original = self.event("CONFLICT")
        self.assertEqual(self.post_event("ALPHA", original).status_code, 201)
        for field in ("type_evenement", "source_system", "source_type", "source_id", "payload"):
            with self.subTest(field=field):
                changed = deepcopy(original)
                if field == "payload":
                    changed[field]["libelle"] = "Autre dépense"
                else:
                    changed[field] = "different"
                self.assertEqual(self.post_event("ALPHA", changed).status_code, 409)
        self.assertEqual(EcritureComptable.objects.count(), 1)
        self.assertEqual(EvenementMetier.objects.get().payload, original["payload"])

    def test_boolean_payload_change_is_not_equal_to_a_numeric_value(self):
        event = self.event("TYPED")
        event["payload"]["marker"] = 1
        self.assertEqual(self.post_event("ALPHA", event).status_code, 201)
        event["payload"]["marker"] = True
        self.assertEqual(self.post_event("ALPHA", event).status_code, 409)

    def test_reordered_json_objects_are_the_same_event(self):
        event = self.event("ORDER")
        self.assertEqual(self.post_event("ALPHA", event).status_code, 201)
        event["payload"] = dict(reversed(list(event["payload"].items())))
        self.assertEqual(self.post_event("ALPHA", event).status_code, 200)

    def test_inbox_does_not_claim_an_unrelated_existing_entry(self):
        self.assertEqual(self.post_event("ALPHA", self.event("ORIGINAL")).status_code, 201)
        original = EcritureComptable.objects.get()
        unrelated = EcritureService.creer_ecriture(
            reference="UNRELATED", date_ecriture=original.date_ecriture, libelle="Direct entry",
            journal=original.journal, exercice=original.exercice, entreprise_id="ALPHA",
            idempotency_key="COLLISION", source_system="manual",
            lignes=[
                {"compte": CompteComptable.objects.get(entreprise_id="ALPHA", code="658"), "debit": Decimal("5")},
                {"compte": CompteComptable.objects.get(entreprise_id="ALPHA", code="571"), "credit": Decimal("5")},
            ],
        )
        response = self.post_event("ALPHA", self.event("COLLISION"))
        self.assertEqual(response.status_code, 422)
        self.assertIsNone(response.json()["entry_id"])
        self.assertEqual(EcritureComptable.objects.count(), 2)
        self.assertEqual(EcritureComptable.objects.get(pk=unrelated.pk).source_system, "manual")

    def test_inbox_checks_ownership_when_a_direct_writer_wins_the_race(self):
        original_create = EcritureService.creer_ecriture

        def racing_create(**kwargs):
            manual = {**kwargs, "source_system": "manual", "metadata": {}}
            original_create(**manual)
            return original_create(**kwargs)  # real service returns the already-existing entry

        with patch.object(EcritureService, "creer_ecriture", side_effect=racing_create):
            response = self.post_event("ALPHA", self.event("LEDGER-RACE"))
        self.assertEqual(response.status_code, 422)
        self.assertIsNone(response.json()["entry_id"])
        self.assertEqual(EvenementMetier.objects.get().statut, "ERREUR")

    def test_replay_succeeds_after_exercise_closes_and_journal_disables(self):
        event = self.event("CLOSED")
        first = self.post_event("ALPHA", event)
        self.assertEqual(first.status_code, 201)
        ExerciceComptable.objects.filter(entreprise_id="ALPHA").update(cloture=True)
        JournalComptable.objects.filter(entreprise_id="ALPHA").update(actif=False)
        replay = self.post_event("ALPHA", event)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json()["entry_id"], first.json()["entry_id"])
        self.assertFalse(JournalComptable.objects.get(entreprise_id="ALPHA").actif)

    def test_line_dimensions_inherit_all_common_axes(self):
        for phase, amount in (("PH1", "30.00"), ("PH2", "20.00")):
            event = self.event(phase, amount)
            event["payload"]["dimensions"]["PHASE"] = phase
            self.assertEqual(self.post_event("ALPHA", event).status_code, 201)
        self.assertEqual(self.costs(PHASE="PH1").json()["total_cost"], "30.00")
        self.assertEqual(self.costs(PHASE="PH2").json()["total_cost"], "20.00")
        self.assertEqual(self.costs(PHASE="PH").json()["total_cost"], "0.00")
        self.assertEqual(AffectationAnalytique.objects.count(), 8)

    def test_contradictory_line_axis_is_rejected_atomically(self):
        event = self.event("FORGED")
        event["payload"]["lignes"][0]["dimensions"]["PROJECT"] = "OTHER"
        response = self.post_event("ALPHA", event)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["statut"], "ERREUR")
        self.assertFalse(EcritureComptable.objects.exists())
        self.assertFalse(AffectationAnalytique.objects.exists())

    def test_boolean_dimension_cannot_override_a_numeric_common_code(self):
        event = self.event("TYPED-AXIS")
        event["payload"]["dimensions"]["PROJECT"] = 1
        event["payload"]["lignes"][0]["dimensions"]["PROJECT"] = True
        event["payload"]["lignes"][1].pop("dimensions")
        self.assertEqual(self.post_event("ALPHA", event).status_code, 422)
        self.assertFalse(EcritureComptable.objects.exists())

    def test_axes_colliding_after_case_normalization_are_rejected(self):
        event = self.event("CASE-AXIS")
        event["payload"]["dimensions"] = {"PROJECT": "A", "project": "B"}
        for line in event["payload"]["lignes"]:
            line.pop("dimensions")
        self.assertEqual(self.post_event("ALPHA", event).status_code, 422)
        self.assertFalse(EcritureComptable.objects.exists())

    def test_no_foreign_account_fallback(self):
        CompteComptable.objects.filter(entreprise_id="ALPHA", code="658").delete()
        self.assertEqual(self.post_event("ALPHA", self.event("FOREIGN")).status_code, 422)
        self.assertFalse(EcritureComptable.objects.exists())

    def test_explicit_account_codes_do_not_fall_back_to_primary_keys(self):
        foreign_code = str(CompteComptable.objects.get(entreprise_id="ALPHA", code="658").pk)
        event = self.event("PK-CODE")
        event["payload"]["lignes"][0]["compte"] = foreign_code
        self.assertEqual(self.post_event("ALPHA", event).status_code, 422)
        self.assertFalse(EcritureComptable.objects.exists())

    def test_generic_ingestion_does_not_create_or_reactivate_journals(self):
        JournalComptable.objects.filter(entreprise_id="ALPHA").update(actif=False)
        self.assertEqual(self.post_event("ALPHA", self.event("DISABLED")).status_code, 422)
        event = self.event("MISSING")
        event["payload"]["journal_code"] = "NEW"
        self.assertEqual(self.post_event("ALPHA", event).status_code, 422)
        self.assertFalse(JournalComptable.objects.filter(entreprise_id="ALPHA", actif=True).exists())
        self.assertFalse(EcritureComptable.objects.exists())

    def test_missing_wrong_and_revoked_keys_are_unauthorized(self):
        self.assertEqual(self.client.get("/api/v1/analytics/costs/", {"PROJECT": "SAME"}).status_code, 401)
        self.assertEqual(self.client.get(
            "/api/v1/analytics/costs/", {"PROJECT": "SAME"}, HTTP_X_API_KEY="wrong",
        ).status_code, 401)
        self.apps["ALPHA"].actif = False
        self.apps["ALPHA"].save(update_fields=["actif"])
        self.assertEqual(self.post_event("ALPHA", self.event("REVOKED")).status_code, 401)
        self.assertFalse(EvenementMetier.objects.exists())

    def test_scopes_and_enterprise_injection_cannot_bypass_isolation(self):
        event = self.event("INJECTED")
        event["entreprise_id"] = "BETA"
        self.assertEqual(self.post_event("ALPHA", event, HTTP_X_ENTERPRISE_ID="BETA").status_code, 201)
        self.assertEqual(EcritureComptable.objects.get().entreprise_id, "ALPHA")
        self.apps["ALPHA"].scopes = ["accounting.read"]
        self.apps["ALPHA"].save(update_fields=["scopes"])
        self.assertEqual(self.post_event("ALPHA", self.event("READONLY")).status_code, 403)
        self.apps["ALPHA"].scopes = ["accounting.events.write"]
        self.apps["ALPHA"].save(update_fields=["scopes"])
        self.assertEqual(self.costs().status_code, 403)

    def test_machine_keys_are_hashed_and_work_with_authorization_header(self):
        app = self.apps["ALPHA"]
        self.assertNotEqual(app.secret_hash, self.keys["ALPHA"])
        self.assertEqual(len(app.secret_hash), 64)
        response = self.client.get(
            "/api/v1/analytics/costs/", {"PROJECT": "SAME"},
            HTTP_AUTHORIZATION="ApiKey " + self.keys["ALPHA"],
        )
        self.assertEqual(response.status_code, 200)

    def test_long_entry_label_is_truncated_only_for_lines(self):
        event = self.event("LONG")
        event["payload"]["libelle"] = "Travaux " * 40
        response = self.post_event("ALPHA", event)
        self.assertEqual(response.status_code, 201)
        entry = EcritureComptable.objects.get()
        self.assertEqual(entry.libelle, event["payload"]["libelle"])
        self.assertTrue(all(len(line.libelle) <= 200 for line in entry.lignes.all()))

    def test_invalid_amounts_and_unbalanced_lines_are_rejected(self):
        for amount in (True, "NaN", "Infinity", "-1", "0", "0.001", "10000000000000"):
            with self.subTest(amount=amount):
                response = self.post_event("ALPHA", self.event(str(amount), amount))
                self.assertEqual(response.status_code, 422)
        event = self.event("UNBALANCED")
        event["payload"]["lignes"][1]["credit"] = "1.00"
        self.assertEqual(self.post_event("ALPHA", event).status_code, 422)
        self.assertFalse(EcritureComptable.objects.exists())

    def test_costs_exclude_drafts_and_assets_and_reverse_to_zero(self):
        self.assertEqual(self.post_event("ALPHA", self.event("VALID")).status_code, 201)
        entry = EcritureComptable.objects.get()
        EcritureService.creer_ecriture(
            reference="DRAFT", date_ecriture=entry.date_ecriture, libelle="Brouillon",
            journal=entry.journal, exercice=entry.exercice, entreprise_id="ALPHA", validee=False,
            lignes=[
                {"compte": CompteComptable.objects.get(entreprise_id="ALPHA", code="658"),
                 "debit": Decimal("10.00"), "dimensions": {"PROJECT": "SAME"}},
                {"compte": CompteComptable.objects.get(entreprise_id="ALPHA", code="571"),
                 "credit": Decimal("10.00"), "dimensions": {"PROJECT": "SAME"}},
            ],
        )
        transfer = self.event("ASSET", "100.00")
        transfer["payload"]["lignes"][0]["compte"] = "521"
        self.assertEqual(self.post_event("ALPHA", transfer).status_code, 201)
        self.assertEqual(self.costs().json()["total_cost"], "40.00")
        ValidationService.annuler_ecriture(entry, raison="Correction")
        self.assertEqual(self.costs().json()["total_cost"], "0.00")

    def test_tenant_currency_takes_priority_over_host_default(self):
        ConfigurationComptable.objects.filter(entreprise_id="BETA").update(devise="XAF")
        self.assertEqual(self.costs("BETA").json()["currency"], "XAF")
        ConfigurationComptable.objects.filter(entreprise_id="ALPHA").delete()
        self.assertEqual(self.costs().json()["currency"], "XOF")

    def test_date_filters_validate_and_limit_the_period(self):
        self.assertEqual(self.post_event("ALPHA", self.event("DATED")).status_code, 201)
        self.assertEqual(self.costs(date_debut="2026-10-04").json()["total_cost"], "0.00")
        self.assertEqual(self.costs(date_debut="invalid").status_code, 400)
        self.assertEqual(self.costs(date_debut="2026-10-04", date_fin="2026-10-01").status_code, 400)


@override_settings(ROOT_URLCONF="comptabilite_ohada.integration_urls")
class RestrictedProjectIntegrationTests(ProjectIntegrationTests):
    def test_restricted_host_has_no_legacy_or_administration_routes(self):
        for path in ("/api/comptabilite/comptes/", "/api/v1/comptes/", "/api/v1/regles-evenements/"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path, HTTP_X_API_KEY=self.keys["ALPHA"]).status_code, 404)
        self.assertEqual(self.client.get("/api/v1/events/", HTTP_X_API_KEY=self.keys["ALPHA"]).status_code, 405)


@override_settings(COMPTABILITE_OHADA={
    "API_ENABLED": True, "COMPTES_INTEGRATION_ENABLED": False, "REQUIRE_TENANT_MEMBERSHIP": True,
})
class ConcurrentProjectIntegrationTests(TransactionTestCase):
    setUp = ProjectIntegrationTests.setUp

    def concurrent_posts(self, payloads):
        barrier = Barrier(2)

        def send(payload):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                response = APIClient().post(
                    "/api/v1/events/", payload, format="json", HTTP_X_API_KEY=self.keys["ALPHA"],
                )
                return response.status_code, response.json()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(send, payloads))

    def test_simultaneous_identical_events_record_once(self):
        event = ProjectIntegrationTests.event("RACE")
        results = self.concurrent_posts([event, deepcopy(event)])
        self.assertEqual(sorted(status for status, _ in results), [200, 201])
        self.assertEqual(results[0][1]["entry_id"], results[1][1]["entry_id"])
        self.assertEqual(EvenementMetier.objects.count(), 1)
        self.assertEqual(EcritureComptable.objects.count(), 1)

    def test_simultaneous_changed_events_conflict(self):
        results = self.concurrent_posts([
            ProjectIntegrationTests.event("RACE", "40.00"),
            ProjectIntegrationTests.event("RACE", "41.00"),
        ])
        self.assertEqual(sorted(status for status, _ in results), [201, 409])
        self.assertEqual(EvenementMetier.objects.count(), 1)
        self.assertEqual(EcritureComptable.objects.count(), 1)

    def test_simultaneous_retries_record_once(self):
        JournalComptable.objects.filter(entreprise_id="ALPHA").update(actif=False)
        response = self.client.post(
            "/api/v1/events/", ProjectIntegrationTests.event("RETRY-RACE"), format="json",
            HTTP_X_API_KEY=self.keys["ALPHA"],
        )
        self.assertEqual(response.status_code, 422)
        event_id = response.json()["id"]
        JournalComptable.objects.filter(entreprise_id="ALPHA").update(actif=True)
        barrier = Barrier(2)

        def retry(_):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                result = APIClient().post(
                    f"/api/v1/events/{event_id}/retry/", {}, format="json",
                    HTTP_X_API_KEY=self.keys["ALPHA"],
                )
                return result.status_code, result.json()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(retry, range(2)))
        self.assertEqual([status for status, _ in results], [200, 200])
        self.assertEqual(results[0][1]["entry_id"], results[1][1]["entry_id"])
        self.assertEqual(EcritureComptable.objects.count(), 1)
