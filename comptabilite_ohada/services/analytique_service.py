from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from ..models import (
    AffectationAnalytique,
    DimensionAnalytique,
    ValeurAnalytique,
)


class AnalytiqueService:
    """Service générique de rattachement analytique sans dépendance métier."""

    @staticmethod
    @transaction.atomic
    def get_or_create_dimension(entreprise_id, code, libelle=None, metadata=None):
        dimension, _ = DimensionAnalytique.objects.get_or_create(
            entreprise_id=entreprise_id or "",
            code=str(code).upper(),
            defaults={
                "libelle": libelle or str(code).replace("_", " ").title(),
                "metadata": metadata or {},
            },
        )
        return dimension

    @staticmethod
    @transaction.atomic
    def get_or_create_valeur(dimension, code, libelle=None, external_id="", metadata=None):
        valeur, _ = ValeurAnalytique.objects.get_or_create(
            dimension=dimension,
            code=str(code),
            defaults={
                "libelle": libelle or str(code),
                "external_id": str(external_id or ""),
                "metadata": metadata or {},
            },
        )
        return valeur

    @classmethod
    @transaction.atomic
    def affecter_ligne(cls, ligne, dimensions):
        if not dimensions:
            return []

        entreprise_id = ligne.ecriture.entreprise_id or ""
        affectations = []

        for code_dimension, raw_values in dimensions.items():
            values = raw_values if isinstance(raw_values, list) else [raw_values]
            if not values:
                raise ValidationError(
                    f"Aucune valeur analytique fournie pour {code_dimension}."
                )

            if len(values) > 1:
                if not all(isinstance(v, dict) for v in values):
                    raise ValidationError(
                        f"Une ventilation multiple sur {code_dimension} doit préciser des pourcentages ou montants."
                    )
                montants = [v.get("montant") for v in values]
                pourcentages = [v.get("pourcentage") for v in values]

                if all(m is not None for m in montants):
                    total_montant = sum(Decimal(str(m)) for m in montants)
                    montant_ligne = ligne.debit or ligne.credit
                    if total_montant != montant_ligne:
                        raise ValidationError(
                            f"La ventilation en montant de {code_dimension} doit totaliser {montant_ligne}."
                        )
                else:
                    if any(p is None for p in pourcentages):
                        raise ValidationError(
                            f"Toutes les répartitions de {code_dimension} doivent fournir un pourcentage."
                        )
                    total_pct = sum(Decimal(str(p)) for p in pourcentages)
                    if total_pct != Decimal("100"):
                        raise ValidationError(
                            f"Les pourcentages de {code_dimension} doivent totaliser 100 (reçu {total_pct})."
                        )

            for raw_value in values:
                if isinstance(raw_value, dict):
                    code_valeur = (
                        raw_value.get("code")
                        or raw_value.get("id")
                        or raw_value.get("external_id")
                    )
                    libelle = raw_value.get("libelle") or raw_value.get("label")
                    external_id = raw_value.get("external_id") or raw_value.get("id") or ""
                    metadata = raw_value.get("metadata") or {}
                    pourcentage = raw_value.get("pourcentage", 100)
                    montant = raw_value.get("montant")
                else:
                    code_valeur = raw_value
                    libelle = str(raw_value)
                    external_id = str(raw_value)
                    metadata = {}
                    pourcentage = 100
                    montant = None

                if code_valeur in (None, ""):
                    raise ValidationError(
                        f"Valeur analytique manquante pour {code_dimension}."
                    )

                dimension = cls.get_or_create_dimension(
                    entreprise_id=entreprise_id,
                    code=code_dimension,
                )
                valeur = cls.get_or_create_valeur(
                    dimension=dimension,
                    code=code_valeur,
                    libelle=libelle,
                    external_id=external_id,
                    metadata=metadata,
                )
                affectation, _ = AffectationAnalytique.objects.update_or_create(
                    ligne=ligne,
                    dimension=dimension,
                    valeur=valeur,
                    defaults={
                        "pourcentage": pourcentage,
                        "montant": montant,
                    },
                )
                affectation.full_clean()
                affectation.save()
                affectations.append(affectation)

        return affectations
