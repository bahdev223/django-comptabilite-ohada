"""Locked policy lifecycle. Host owns authorization/audit; engine owns posting safety."""
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from ..models import AccountingPolicyAssignment, ExerciceComptable, EcritureComptable
from ..tenancy import require_owned

NORMAL_RULESET = 'jatebo-normal-1'


def validate_decision(value):
    if not isinstance(value, dict):
        raise ValidationError('Décision comptable documentée obligatoire.')
    result = {}
    for key, minimum, maximum in [('country', 2, 2), ('currency', 3, 3),
            ('activity', 2, 160), ('source', 5, 250), ('reason', 20, 1500)]:
        text = value.get(key)
        if not isinstance(text, str) or not minimum <= len(text.strip()) <= maximum:
            raise ValidationError(f'Décision comptable : champ {key} incomplet.')
        result[key] = text.strip()
    for key in ('country', 'currency'):
        if not re.fullmatch('[A-Z]+', result[key]):
            raise ValidationError(f'Décision comptable : code {key} invalide.')
    if value.get('basis') not in ('normal_required', 'normal_option', 'professional_review', 'smt_requested'):
        raise ValidationError('Indiquez le fondement de la décision comptable.')
    result['basis'] = value['basis']
    result['confirmed'] = value.get('confirmed') is True
    for key in ('turnover_period', 'reference'):
        if key in value:
            if not isinstance(value[key], str) or len(value[key]) > 250:
                raise ValidationError(f'Décision comptable : champ {key} invalide.')
            result[key] = value[key].strip()
    if value.get('turnover_ht') not in (None, ''):
        try:
            raw = value['turnover_ht']
            if not isinstance(raw, str) or len(raw) > 30: raise ValueError()
            amount = Decimal(raw)
            if not amount.is_finite() or amount < 0 or amount >= Decimal('1e18') or amount != amount.quantize(Decimal('.01')):
                raise ValueError()
            result['turnover_ht'] = format(amount, '.2f')
        except (ValueError, InvalidOperation):
            raise ValidationError('Chiffre d’affaires HT invalide.')
    result['assessment'] = 'manual_unverified'
    result['criteria_version'] = 'AUDCIF-2017-manual-review'
    return result


def snapshot(policy):
    identity = {'exercise': policy.exercise_id, 'system': policy.system,
        'ruleset_version': policy.ruleset_version, 'status': policy.status,
        'decision': policy.decision, 'revision': policy.revision,
        'decided_at': policy.decided_at.isoformat() if policy.decided_at else None}
    identity['fingerprint'] = hashlib.sha256(json.dumps(identity, sort_keys=True,
        separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()
    return {**identity, 'frozen_at': policy.frozen_at.isoformat() if policy.frozen_at else None}


def policy_status(exercice, *, entreprise_id):
    year = require_owned(exercice, entreprise_id)
    policy = AccountingPolicyAssignment.objects.filter(exercise=year).first()
    if policy:
        return snapshot(policy)
    return {'exercise': year.pk, 'status': 'legacy_unclassified', 'system': None,
            'ruleset_version': None, 'fingerprint': None, 'frozen_at': None}


def _locked_year(exercice, entreprise_id):
    year = require_owned(exercice, entreprise_id)
    return ExerciceComptable.objects.select_for_update().get(pk=year.pk, entreprise_id=entreprise_id)


def _raw(policy):
    # Same guarded-service convention as ValidationService for posted entries.
    return models.QuerySet(model=AccountingPolicyAssignment, using=policy._state.db).filter(pk=policy.pk)


@transaction.atomic
def prepare(exercice, *, system, decision, entreprise_id):
    year = _locked_year(exercice, entreprise_id)
    if system not in ('NORMAL', 'SMT'):
        raise ValidationError('Système comptable inconnu.')
    data = validate_decision(decision)
    if year.cloture or EcritureComptable.objects.filter(exercice=year, validee=True).exists():
        raise ValidationError('Exercice clos ou déjà mouvementé : reprise comptable contrôlée requise.')
    policy = AccountingPolicyAssignment.objects.filter(exercise=year).first()
    if policy and policy.frozen_at:
        raise ValidationError('Le système de cet exercice est figé.')
    fields = dict(system=system, decision=data, status='draft', decided_at=None,
                  ruleset_version=NORMAL_RULESET if system == 'NORMAL' else '')
    if policy:
        _raw(policy).update(**fields, revision=policy.revision + 1)
        policy.refresh_from_db()
    else:
        policy = AccountingPolicyAssignment.objects.create(exercise=year, **fields)
    return snapshot(policy)


@transaction.atomic
def confirm(exercice, *, fingerprint, entreprise_id):
    year = _locked_year(exercice, entreprise_id)
    policy = AccountingPolicyAssignment.objects.filter(exercise=year).first()
    if policy is None or not isinstance(fingerprint, str) or snapshot(policy)['fingerprint'] != fingerprint:
        raise ValidationError('Décision absente ou périmée ; rechargez le dossier.')
    if policy.system != 'NORMAL' or policy.ruleset_version != NORMAL_RULESET:
        raise ValidationError('Ce jeu de règles comptables n’est pas encore disponible.')
    if policy.status == 'confirmed':
        return snapshot(policy)
    if year.cloture or EcritureComptable.objects.filter(exercice=year, validee=True).exists():
        raise ValidationError('Une reprise contrôlée est requise pour cet exercice.')
    if policy.decision.get('confirmed') is not True:
        raise ValidationError('Confirmez explicitement la décision comptable.')
    _raw(policy).update(status='confirmed', decided_at=timezone.now())
    policy.refresh_from_db()
    return snapshot(policy)


def freeze_for_posting(exercice, *, entreprise_id):
    """Called under the fiscal-year lock in the SAME transaction as posting."""
    year = require_owned(exercice, entreprise_id)
    policy = AccountingPolicyAssignment.objects.filter(exercise=year).first()
    if policy is None:
        return  # Explicit legacy compatibility, never a silent Normal assignment.
    if (policy.status != 'confirmed' or policy.system != 'NORMAL'
            or policy.ruleset_version != NORMAL_RULESET):
        raise ValidationError('Système comptable non confirmé ou non disponible : écriture refusée.')
    if not policy.frozen_at:
        _raw(policy).update(frozen_at=timezone.now())
