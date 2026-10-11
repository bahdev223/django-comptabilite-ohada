"""P0 security regression tests for multi-company accounting and safe API access."""
import unittest
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.urls import include, path
from django.utils import timezone

from ..integrations import connect_integrations
from ..models import (
    CompteComptable, EcritureComptable, ExerciceComptable, JournalComptable,
)
from ..services.ecriture_service import EcritureService
from ..services.exercice_service import ValidationService, ExerciceService
from ..services.journal_service import BalanceService
from ..tenancy import tenant_scope

try:
    from rest_framework.exceptions import PermissionDenied
    from rest_framework.test import APIClient
except ImportError:
    PermissionDenied = Exception
    APIClient = None


def resolve_membership_for_tests(request):
    """Demonstration resolver: a requested company is accepted ONLY if authorized."""
    requested = request.headers.get("X-Enterprise-ID")
    if not requested or not request.user.groups.filter(name=f"accounting:{requested}").exists():
        raise PermissionDenied("Not a member of this enterprise.")
    return requested


if APIClient is not None:
    urlpatterns = [path("", include("comptabilite_ohada.api.urls"))]
else:
    urlpatterns = []


class SecureLedgerTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        with tenant_scope("acme"):
            self.exercise_a = ExerciceComptable.objects.create(
                code=str(self.today.year),
                date_debut=date(self.today.year, 1, 1),
                date_fin=date(self.today.year, 12, 31),
            )
            self.journal_a = JournalComptable.objects.create(
                code="VN", libelle="Ventes ACME", type_journal="VENTES",
            )
            self.cash_a = CompteComptable.objects.create(
                code="571", libelle="Caisse ACME", nature="ACTIF", sens="DEBIT",
            )
            self.revenue_a = CompteComptable.objects.create(
                code="706", libelle="Recettes ACME", nature="PRODUIT", sens="CREDIT",
            )
        with tenant_scope("other"):
            self.exercise_b = ExerciceComptable.objects.create(
                code=str(self.today.year),
                date_debut=date(self.today.year, 1, 1),
                date_fin=date(self.today.year, 12, 31),
            )
            self.journal_b = JournalComptable.objects.create(
                code="VN", libelle="Ventes OTHER", type_journal="VENTES",
            )
            self.cash_b = CompteComptable.objects.create(
                code="571", libelle="Caisse OTHER", nature="ACTIF", sens="DEBIT",
            )
            self.revenue_b = CompteComptable.objects.create(
                code="706", libelle="Recettes OTHER", nature="PRODUIT", sens="CREDIT",
            )

    def create_sale(self, reference, amount="1000.00"):
        return EcritureService.creer_ecriture(
            reference=reference,
            date_ecriture=self.today,
            libelle="Vente documentée",
            journal=self.journal_a,
            exercice=self.exercise_a,
            lignes=[
                {"compte": self.cash_a, "debit": Decimal(amount)},
                {"compte": self.revenue_a, "credit": Decimal(amount)},
            ],
            validee=True,
        )

    def test_helpers_fail_closed_without_company_context(self):
        with self.assertRaises(ValidationError):
            EcritureService.get_compte("571")
        with self.assertRaises(ValidationError):
            BalanceService.balance()

    def test_same_chart_codes_are_independently_scoped(self):
        with tenant_scope("acme"):
            self.assertEqual(EcritureService.get_compte("571").pk, self.cash_a.pk)
            self.assertEqual(EcritureService.get_exercice(self.today).pk, self.exercise_a.pk)
            self.assertNotEqual(EcritureService.get_compte("571").pk, self.cash_b.pk)
        with tenant_scope("other"):
            self.assertEqual(EcritureService.get_compte("571").pk, self.cash_b.pk)

    def test_foreign_journal_and_account_are_rejected(self):
        with tenant_scope("acme"):
            with self.assertRaises(ValidationError):
                EcritureService.creer_ecriture(
                    reference="CROSS-JOURNAL", date_ecriture=self.today,
                    libelle="Untrusted", journal=self.journal_b, exercice=self.exercise_a,
                    lignes=[
                        {"compte": self.cash_a, "debit": 100},
                        {"compte": self.revenue_a, "credit": 100},
                    ],
                )
            with self.assertRaises(ValidationError):
                EcritureService.creer_ecriture(
                    reference="CROSS-ACCOUNT", date_ecriture=self.today,
                    libelle="Untrusted", journal=self.journal_a, exercice=self.exercise_a,
                    lignes=[
                        {"compte": self.cash_b, "debit": 100},
                        {"compte": self.revenue_a, "credit": 100},
                    ],
                )
        self.assertEqual(EcritureComptable.objects.count(), 0)

    def test_period_is_never_taken_from_another_company_or_wrong_year(self):
        with tenant_scope("acme"):
            self.assertIsNone(
                EcritureService.get_exercice(date(self.today.year + 1, 1, 1))
            )
            with self.assertRaises(ValidationError):
                EcritureService.creer_ecriture(
                    reference="WRONG-YEAR",
                    date_ecriture=date(self.today.year + 1, 1, 1),
                    libelle="Invalid", journal=self.journal_a,
                    lignes=[
                        {"compte": self.cash_a, "debit": 10},
                        {"compte": self.revenue_a, "credit": 10},
                    ],
                )

    def test_unbalanced_or_invalid_lines_are_atomic(self):
        with tenant_scope("acme"):
            with self.assertRaises(ValidationError):
                EcritureService.creer_ecriture(
                    reference="BAD-BALANCE", date_ecriture=self.today,
                    libelle="Bad", journal=self.journal_a,
                    lignes=[
                        {"compte": self.cash_a, "debit": 100},
                        {"compte": self.revenue_a, "credit": 99},
                    ],
                )
            with self.assertRaises(ValidationError):
                EcritureService.creer_ecriture(
                    reference="BAD-SIGN", date_ecriture=self.today,
                    libelle="Bad", journal=self.journal_a,
                    lignes=[
                        {"compte": self.cash_a, "debit": 100, "credit": 1},
                        {"compte": self.revenue_a, "credit": 101},
                    ],
                )
        self.assertFalse(EcritureComptable.objects.exists())

    def test_validated_entry_and_lines_are_immutable(self):
        with tenant_scope("acme"):
            entry = self.create_sale("VALIDATED")
            entry.libelle = "Changed"
            with self.assertRaises(ValidationError):
                entry.save()
            line = entry.lignes.first()
            line.debit = Decimal("500.00")
            with self.assertRaises(ValidationError):
                line.save()

    def test_reversal_is_in_open_period_and_deduplicated(self):
        with tenant_scope("acme"):
            original = self.create_sale("SALE-REVERSIBLE")
            reversal = ValidationService.annuler_ecriture(original, raison="Erreur")
            self.assertEqual(reversal.exercice_id, self.exercise_a.pk)
            self.assertTrue(reversal.validee)
            self.assertEqual(reversal.reference, f"REV-{original.pk}")
            with self.assertRaises((ValidationError, IntegrityError)):
                ValidationService.annuler_ecriture(original, raison="Erreur répétée")
            balances = BalanceService.balance(exercice=self.exercise_a)
            self.assertEqual(
                sum((line["total_debit"] for line in balances), Decimal("0.00")),
                sum((line["total_credit"] for line in balances), Decimal("0.00")),
            )

    def test_unsafe_closing_is_explicitly_blocked(self):
        with tenant_scope("acme"):
            with self.assertRaises(ValidationError):
                ExerciceService.cloturer(self.exercise_a)
            self.exercise_a.refresh_from_db()
            self.assertFalse(self.exercise_a.cloture)

    def test_auto_signals_do_not_post_anything(self):
        with override_settings(COMPTABILITE_OHADA={}):
            self.assertIsNone(connect_integrations())
        with override_settings(
            COMPTABILITE_OHADA={"COMPTES_INTEGRATION_ENABLED": True}
        ):
            with self.assertRaises(ImproperlyConfigured):
                connect_integrations()


@unittest.skipIf(APIClient is None, "DRF optional dependency not installed")
@override_settings(
    ROOT_URLCONF="comptabilite_ohada.tests.test_tenant_security",
    COMPTABILITE_OHADA={
        "API_ENABLED": True,
        "TENANT_RESOLVER": (
            "comptabilite_ohada.tests.test_tenant_security.resolve_membership_for_tests"
        ),
    },
)
class SecureAccountingAPITests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="audited-user", email="audited@example.test", password="not-used",
        )
        self.membership = Group.objects.create(name="accounting:acme")
        self.user.groups.add(self.membership)
        self.today = timezone.localdate()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_ENTERPRISE_ID="acme")

        with tenant_scope("acme"):
            self.journal_a = JournalComptable.objects.create(
                code="VN", libelle="ACME Journal", type_journal="VENTES",
            )
            ExerciceComptable.objects.create(
                code=str(self.today.year), date_debut=date(self.today.year, 1, 1),
                date_fin=date(self.today.year, 12, 31),
            )
            self.cash_a = CompteComptable.objects.create(
                code="571", libelle="Only ACME", nature="ACTIF", sens="DEBIT",
            )
            self.rev_a = CompteComptable.objects.create(
                code="706", libelle="Revenue ACME", nature="PRODUIT", sens="CREDIT",
            )
        with tenant_scope("other"):
            self.cash_b = CompteComptable.objects.create(
                code="571", libelle="Secret OTHER", nature="ACTIF", sens="DEBIT",
            )
            JournalComptable.objects.create(
                code="VN", libelle="OTHER Journal", type_journal="VENTES",
            )

    def test_read_is_scoped_and_forged_header_forbidden(self):
        response = self.client.get("/api/comptabilite/comptes/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Only ACME", str(response.data))
        self.assertNotIn("Secret OTHER", str(response.data))
        self.client.credentials(HTTP_X_ENTERPRISE_ID="other")
        response = self.client.get("/api/comptabilite/comptes/")
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("Secret OTHER", str(response.data))

    def test_ledger_creation_rejects_foreign_account(self):
        data = {
            "reference": "BAD-API", "date_ecriture": self.today.isoformat(),
            "libelle": "Tentative", "journal": self.journal_a.pk,
            "lignes": [
                {"compte": self.cash_b.pk, "debit": "100.00"},
                {"compte": self.rev_a.pk, "credit": "100.00"},
            ],
        }
        response = self.client.post("/api/comptabilite/ecritures/", data, format="json")
        self.assertEqual(response.status_code, 404)
        self.assertFalse(EcritureComptable.objects.exists())

    def test_ledger_creation_validation_and_balance(self):
        payload = {
            "reference": "OK-API", "date_ecriture": self.today.isoformat(),
            "libelle": "Vente documentée", "journal": self.journal_a.pk,
            "lignes": [
                {"compte": self.cash_a.pk, "debit": "200.00"},
                {"compte": self.rev_a.pk, "credit": "200.00"},
            ],
        }
        created = self.client.post("/api/comptabilite/ecritures/", payload, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertFalse(created.data["validee"])
        entry_id = created.data["id"]
        validated = self.client.post(f"/api/comptabilite/ecritures/{entry_id}/valider/")
        self.assertEqual(validated.status_code, 200, validated.data)
        balance = self.client.get("/api/comptabilite/ecritures/balance/")
        self.assertEqual(balance.status_code, 200)
        self.assertNotIn("Secret OTHER", str(balance.data))

    def test_legacy_unscoped_writes_are_disabled(self):
        response = self.client.post(
            "/api/comptabilite/journaux/",
            {"code": "OD", "libelle": "Danger", "type_journal": "OD"},
        )
        self.assertEqual(response.status_code, 405)

    @override_settings(COMPTABILITE_OHADA={"API_ENABLED": True})
    def test_missing_trusted_resolver_is_forbidden(self):
        response = self.client.get("/api/comptabilite/comptes/")
        self.assertEqual(response.status_code, 403)
