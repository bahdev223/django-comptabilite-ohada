"""Explicit engine scope. The host authenticates and authorizes before calling.

No implicit global tenant, header lookup, staff bypass or legacy-data assignment.
"""
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError


def require_enterprise(value):
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > 255:
        raise ValidationError('entreprise_id explicite et non vide obligatoire.')
    return value


def require_owned(obj, entreprise_id):
    require_enterprise(entreprise_id)
    if obj is None or not obj.pk or getattr(obj, 'entreprise_id', None) != entreprise_id:
        raise ValidationError('Référence comptable hors entreprise ou absente.')
    # Re-read: never trust stale instances or caller-supplied model attributes.
    current = type(obj).objects.filter(pk=obj.pk, entreprise_id=entreprise_id).first()
    if current is None:
        raise ValidationError('Référence comptable hors entreprise ou absente.')
    return current


def scoped_lines(entreprise_id):
    from .models import LigneEcritureComptable
    tenant = require_enterprise(entreprise_id)
    return LigneEcritureComptable.objects.filter(
        ecriture__entreprise_id=tenant, compte__entreprise_id=tenant,
        ecriture__journal__entreprise_id=tenant, ecriture__exercice__entreprise_id=tenant,
    )


def scoped_entries(entreprise_id):
    """Never return related metadata from inconsistent historical tenant graphs."""
    from .models import EcritureComptable, LigneEcritureComptable
    tenant = require_enterprise(entreprise_id)
    foreign_lines = LigneEcritureComptable.objects.exclude(compte__entreprise_id=tenant)
    return EcritureComptable.objects.filter(
        entreprise_id=tenant, journal__entreprise_id=tenant, exercice__entreprise_id=tenant,
    ).exclude(lignes__in=foreign_lines)


def money(value):
    try:
        amount = Decimal(str(value if value is not None else 0))
        if not amount.is_finite() or amount < 0 or amount >= Decimal('10000000000000'):
            raise ValidationError('Montant monétaire invalide.')
        if amount != amount.quantize(Decimal('0.01')):
            raise ValidationError('Deux décimales maximum ; aucun arrondi implicite.')
        return amount
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValidationError('Montant monétaire invalide.') from exc


def validate_entry(date_ecriture, journal, exercice, lignes, entreprise_id):
    journal = require_owned(journal, entreprise_id)
    exercice = require_owned(exercice, entreprise_id)
    if not journal.actif or exercice.cloture or not exercice.date_debut <= date_ecriture <= exercice.date_fin:
        raise ValidationError('Journal inactif, exercice clos ou date hors exercice.')
    if len(lignes) < 2:
        raise ValidationError('Au moins deux lignes comptables obligatoires.')
    debit = credit = Decimal('0')
    normalized = []
    for ligne in lignes:
        if ligne.get('compte') is None:
            raise ValidationError('Compte comptable introuvable.')
        compte = require_owned(ligne.get('compte'), entreprise_id)
        if not compte.actif:
            raise ValidationError('Compte comptable inactif.')
        d, c = money(ligne.get('debit', 0)), money(ligne.get('credit', 0))
        if bool(d) == bool(c):
            raise ValidationError('Une ligne porte exactement un débit ou un crédit positif.')
        debit += d
        credit += c
        normalized.append(dict(ligne, compte=compte, debit=d, credit=c))
    if debit != credit or debit == 0:
        raise ValidationError('Écriture déséquilibrée ou sans montant.')
    return journal, exercice, normalized
