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
