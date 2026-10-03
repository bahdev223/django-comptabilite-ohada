"""Tenant-scoped bridge from external project events to the OHADA ledger."""

import hashlib
import hmac
import json
from datetime import date
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.db.models import Sum

from ..models import (
    CompteComptable,
    EcritureComptable,
    ExerciceComptable,
    IntegrationReceipt,
    JournalComptable,
    LigneEcritureComptable,
    NatureCompte,
)

DIMENSION_KEYS = {"PROJECT", "PHASE", "ACTIVITY", "TASK", "MISSION", "CONTRACT"}
CENT = Decimal("0.01")


class IntegrationError(Exception):
    def __init__(self, message, status=400):
        self.status = status
        super().__init__(message)


def tenant_for_key(api_key):
    keys = getattr(settings, "COMPTABILITE_OHADA", {}).get("INTEGRATION_KEYS", {})
    if not isinstance(keys, dict) or not api_key or not isinstance(api_key, str):
        raise IntegrationError("Clé d'intégration invalide.", 401)
    matches = [
        tenant
        for tenant, configured in keys.items()
        if isinstance(tenant, str)
        and tenant.strip()
        and isinstance(configured, str)
        and configured
        and hmac.compare_digest(api_key, configured)
    ]
    if len(matches) != 1:
        raise IntegrationError("Clé d'intégration invalide.", 401)
    return matches[0]


def _text(value, name, limit=255):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise IntegrationError(f"{name} invalide.")
    return value.strip()


def _dimensions(value, *, project_required=False):
    if not isinstance(value, dict) or set(value) - DIMENSION_KEYS:
        raise IntegrationError("Dimensions analytiques invalides.")
    dimensions = {key: _text(item, key, 100) for key, item in value.items()}
    if project_required and "PROJECT" not in dimensions:
        raise IntegrationError("Dimension PROJECT obligatoire.")
    return dimensions


def _amount(value):
    try:
        amount = Decimal(str(value))
        if (
            isinstance(value, bool)
            or not amount.is_finite()
            or amount < 0
            or amount >= Decimal(10000000000000)
            or amount != amount.quantize(CENT)
        ):
            raise ValueError
        return amount
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise IntegrationError("Montant comptable invalide.") from exc


def _prepare_event(tenant, envelope):
    if not isinstance(envelope, dict):
        raise IntegrationError("Événement invalide.")
    _text(envelope.get("type_evenement"), "type_evenement", 160)
    if envelope.get("source_system") != "saheltech-platform" or envelope.get("source_type") != "project":
        raise IntegrationError("Source d'événement non prise en charge.")
    _text(envelope.get("source_id"), "source_id")
    key = _text(envelope.get("idempotency_key"), "idempotency_key")
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise IntegrationError("Contenu de l'événement invalide.")
    try:
        operation_date = date.fromisoformat(_text(payload.get("date"), "date", 10))
    except ValueError as exc:
        raise IntegrationError("Date comptable invalide.") from exc
    label = _text(payload.get("libelle"), "libelle", 2000)
    journal_code = _text(payload.get("journal_code"), "journal_code", 10)
    dimensions = _dimensions(payload.get("dimensions"), project_required=True)
    if payload.get("source_reference") != dimensions["PROJECT"]:
        raise IntegrationError("Référence projet incohérente.")
    raw_lines = payload.get("lignes")
    if not isinstance(raw_lines, list) or len(raw_lines) < 2:
        raise IntegrationError("Au moins deux lignes comptables sont requises.")
    lines = []
    debit_total = Decimal("0.00")
    credit_total = Decimal("0.00")
    for raw in raw_lines:
        if not isinstance(raw, dict):
            raise IntegrationError("Ligne comptable invalide.")
        code = _text(raw.get("compte"), "compte", 20)
        account = CompteComptable.objects.filter(
            entreprise_id=tenant, code=code, actif=True, est_mouvement=True
        ).first()
        if account is None:
            raise IntegrationError("Compte comptable absent de cette entreprise.")
        debit = _amount(raw.get("debit", "0"))
        credit = _amount(raw.get("credit", "0"))
        if (debit > 0) == (credit > 0):
            raise IntegrationError("Chaque ligne doit avoir un débit ou un crédit positif.")
        line_dimensions = _dimensions(raw.get("dimensions", {}))
        if any(key in dimensions and dimensions[key] != value for key, value in line_dimensions.items()):
            raise IntegrationError("La ligne contredit les dimensions du projet.")
        lines.append((account, debit, credit, {**dimensions, **line_dimensions}))
        debit_total += debit
        credit_total += credit
    if debit_total != credit_total or debit_total == 0:
        raise IntegrationError("Écriture comptable déséquilibrée.")
    journal = JournalComptable.objects.filter(
        entreprise_id=tenant, code=journal_code, actif=True
    ).first()
    if journal is None:
        raise IntegrationError("Journal absent de cette entreprise.")
    exercises = list(
        ExerciceComptable.objects.filter(
            entreprise_id=tenant,
            date_debut__lte=operation_date,
            date_fin__gte=operation_date,
            cloture=False,
        )[:2]
    )
    if len(exercises) != 1:
        raise IntegrationError("Un seul exercice ouvert doit couvrir cette date.")
    return key, operation_date, label, journal, exercises[0], lines, debit_total


@transaction.atomic
def record_event(tenant, envelope):
    if not isinstance(envelope, dict):
        raise IntegrationError("Événement invalide.")
    key = _text(envelope.get("idempotency_key"), "idempotency_key")
    digest = hashlib.sha256(
        json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    existing = IntegrationReceipt.objects.filter(
        entreprise_id=tenant, idempotency_key=key
    ).select_related("ecriture").first()
    if existing is not None:
        if existing.payload_hash != digest:
            raise IntegrationError("Cette clé désigne un autre événement.", 409)
        if existing.ecriture is None:
            raise IntegrationError("Événement comptable incomplet.", 409)
        return existing.ecriture, False

    _, operation_date, label, journal, exercise, lines, _ = _prepare_event(
        tenant, envelope
    )
    receipt, created = IntegrationReceipt.objects.get_or_create(
        entreprise_id=tenant,
        idempotency_key=key,
        defaults={"payload_hash": digest},
    )
    if not created:
        if receipt.payload_hash != digest:
            raise IntegrationError("Cette clé désigne un autre événement.", 409)
        if receipt.ecriture is None:
            raise IntegrationError("Événement comptable incomplet.", 409)
        return receipt.ecriture, False
    entry = EcritureComptable.objects.create(
        entreprise_id=tenant,
        reference=f"ST-{hashlib.sha256(key.encode()).hexdigest()[:32]}",
        date_ecriture=operation_date,
        libelle=label,
        journal=journal,
        exercice=exercise,
        validee=True,
        created_by="saheltech-platform",
    )
    LigneEcritureComptable.objects.bulk_create(
        [
            LigneEcritureComptable(
                ecriture=entry,
                compte=account,
                debit=debit,
                credit=credit,
                libelle=label[:200],
                dimensions=dimensions,
            )
            for account, debit, credit, dimensions in lines
        ]
    )
    receipt.ecriture = entry
    receipt.save(update_fields=["ecriture"])
    return entry, True


def analytic_costs(tenant, filters):
    if "PROJECT" not in filters or set(filters) - DIMENSION_KEYS:
        raise IntegrationError("Dimension PROJECT obligatoire.")
    dimensions = {key: _text(value, key, 100) for key, value in filters.items()}
    lines = LigneEcritureComptable.objects.filter(
        ecriture__entreprise_id=tenant,
        ecriture__validee=True,
        compte__entreprise_id=tenant,
        compte__nature=NatureCompte.CHARGE,
    )
    for key, value in dimensions.items():
        lines = lines.filter(**{f"dimensions__{key}": value})
    totals = lines.aggregate(debit=Sum("debit"), credit=Sum("credit"))
    total = (totals["debit"] or Decimal("0.00")) - (
        totals["credit"] or Decimal("0.00")
    )
    currency = getattr(settings, "COMPTABILITE_OHADA", {}).get(
        "DEVISE_PAR_DEFAUT", "XAF"
    )
    return {"total_cost": str(total.quantize(CENT)), "currency": currency}
