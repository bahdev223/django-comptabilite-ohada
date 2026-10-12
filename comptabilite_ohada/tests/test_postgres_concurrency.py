"""Real PostgreSQL lock tests; intentionally skipped under SQLite.

Use a real PostgreSQL 16 database. Threads need independent Django
connections and TransactionTestCase (not TestCase's wrapping transaction).
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from threading import Event, Barrier

from django.core.exceptions import ValidationError
from django.db import IntegrityError, close_old_connections, connection, connections, transaction
from django.test import TransactionTestCase, skipUnlessDBFeature

from ..models import (
    CompteComptable, EcritureComptable, ExerciceComptable,
    JournalComptable, LigneEcritureComptable,
)
from ..services.ecriture_service import EcritureService
from ..services.exercice_service import ValidationService


class PostgreSQLAccountingConcurrencyTests(TransactionTestCase):
    """Enforce serial validation and prevent ledger duplication under concurrency."""

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL is mandatory for SELECT FOR UPDATE tests.")
        self.tenant = "PG-RECETTE"
        self.year = ExerciceComptable.objects.create(
            entreprise_id=self.tenant, code="2026",
            date_debut=date(2026, 1, 1), date_fin=date(2026, 12, 31),
        )
        self.journal = JournalComptable.objects.create(
            entreprise_id=self.tenant, code="CS", libelle="Caisse", type_journal="CAISSE",
        )
        self.cash = CompteComptable.objects.create(
            entreprise_id=self.tenant, code="571", libelle="Caisse",
        )
        self.customer = CompteComptable.objects.create(
            entreprise_id=self.tenant, code="411", libelle="Clients",
        )

    def payload(self, reference, validated=False):
        return {
            "entreprise_id": self.tenant,
            "reference": reference,
            "date_ecriture": date(2026, 6, 12),
            "libelle": "Recette contrôlée",
            "journal": self.journal,
            "exercice": self.year,
            "lignes": [
                {"compte": self.cash, "debit": Decimal("100.00")},
                {"compte": self.customer, "credit": Decimal("100.00")},
            ],
            "validee": validated,
        }

    def _thread(self, callback):
        close_old_connections()
        try:
            return callback()
        finally:
            connections.close_all()

    def test_line_append_waits_for_validation_then_refuses(self):
        entry = EcritureService.creer_ecriture(**self.payload("SERIAL-1"))
        locked = Event()
        attempt = Event()
        release = Event()

        def validator():
            def work():
                with transaction.atomic():
                    ExerciceComptable.objects.select_for_update().get(pk=self.year.pk)
                    locked.set()
                    if not release.wait(timeout=8):
                        raise TimeoutError("Holding lock exceeded 8 seconds.")
                    ValidationService.valider_ecriture(entry, entreprise_id=self.tenant)
                return True
            return self._thread(work)

        def appender():
            def work():
                if not locked.wait(timeout=8):
                    raise TimeoutError("Validation transaction not started.")
                attempt.set()
                try:
                    LigneEcritureComptable.objects.create(
                        ecriture=entry, compte=self.cash,
                        debit=Decimal("1.00"), credit=Decimal("0.00"),
                    )
                    return "unexpectedly_added"
                except ValidationError:
                    return "rejected"
            return self._thread(work)

        with ThreadPoolExecutor(max_workers=2) as pool:
            future_validation = pool.submit(validator)
            self.assertTrue(locked.wait(timeout=8))
            future_append = pool.submit(appender)
            self.assertTrue(attempt.wait(timeout=8))
            # A competing line writer is blocked on the same fiscal-year lock.
            self.assertFalse(future_append.done())
            release.set()
            self.assertTrue(future_validation.result(timeout=15))
            self.assertEqual(future_append.result(timeout=15), "rejected")

        entry.refresh_from_db()
        self.assertTrue(entry.validee)
        self.assertEqual(entry.lignes.count(), 2)
        self.assertEqual(entry.total_debit, Decimal("100.00"))
        self.assertEqual(entry.total_credit, Decimal("100.00"))

    def test_two_writers_same_enterprise_reference_are_deduplicated(self):
        barrier = Barrier(2)

        def writer():
            def work():
                barrier.wait(timeout=8)
                try:
                    EcritureService.creer_ecriture(**self.payload("DUPLICATE", validated=True))
                    return "created"
                except (IntegrityError, ValidationError):
                    return "rejected"
            return self._thread(work)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [pool.submit(writer) for _ in range(2)]
            results = [future.result(timeout=15) for future in results]
        self.assertCountEqual(results, ["created", "rejected"])
        self.assertEqual(EcritureComptable.objects.filter(
            entreprise_id=self.tenant, reference="DUPLICATE",
        ).count(), 1)

    def test_two_validators_cannot_both_validate_same_draft(self):
        entry = EcritureService.creer_ecriture(**self.payload("VALIDATE-ONCE"))
        barrier = Barrier(2)

        def validate():
            def work():
                barrier.wait(timeout=8)
                try:
                    ValidationService.valider_ecriture(entry, entreprise_id=self.tenant)
                    return "validated"
                except ValidationError:
                    return "rejected"
            return self._thread(work)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(validate) for _ in range(2)]
            results = [future.result(timeout=15) for future in futures]
        self.assertCountEqual(results, ["validated", "rejected"])
        entry.refresh_from_db()
        self.assertTrue(entry.validee)

    def test_repeated_concurrent_reversal_preserves_original_and_posts_once(self):
        entry = EcritureService.creer_ecriture(**self.payload('REVERSE-ONCE', validated=True))
        barrier = Barrier(2)

        def reverse():
            def work():
                barrier.wait(timeout=8)
                try:
                    ValidationService.annuler_ecriture(entry, entreprise_id=self.tenant,
                        raison='Correction recette', date_operation=date(2026, 6, 13))
                    return 'reversed'
                except ValidationError:
                    return 'rejected'
            return self._thread(work)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(reverse) for _ in range(2)]
            self.assertCountEqual([f.result(timeout=15) for f in futures], ['reversed', 'rejected'])
        entry.refresh_from_db()
        self.assertTrue(entry.validee)
        self.assertEqual(entry.total_debit, Decimal('100'))
        self.assertEqual(EcritureComptable.objects.filter(entreprise_id=self.tenant, reference=f'ANNULE-ID-{entry.pk}').count(), 1)

    def test_opposite_year_reversals_use_consistent_lock_order(self):
        next_year = ExerciceComptable.objects.create(entreprise_id=self.tenant, code='2027', date_debut=date(2027, 1, 1), date_fin=date(2027, 12, 31))
        first = EcritureService.creer_ecriture(**self.payload('FROM-2026', validated=True))
        data = self.payload('FROM-2027', validated=True)
        data.update(exercice=next_year, date_ecriture=date(2027, 6, 12))
        second = EcritureService.creer_ecriture(**data)
        barrier = Barrier(2)

        def reverse(entry, operation_date):
            def work():
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute("SET LOCAL lock_timeout = '5s'")
                    barrier.wait(timeout=8)
                    return ValidationService.annuler_ecriture(entry, entreprise_id=self.tenant,
                        raison='Recette inter-exercices', date_operation=operation_date).pk
            return self._thread(work)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(reverse, first, date(2027, 6, 13)),
                       pool.submit(reverse, second, date(2026, 6, 13))]
            self.assertEqual(len({f.result(timeout=15) for f in futures}), 2)
