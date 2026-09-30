from decimal import Decimal

from rest_framework import serializers

from ..services.ecriture_service import EcritureService
from ..models import (
    CompteComptable, EcritureComptable, LigneEcritureComptable,
    JournalComptable, ExerciceComptable, ConfigurationComptable,
    Immobilisation, PlanAmortissement,
    DimensionAnalytique, ValeurAnalytique, AffectationAnalytique,
    EvenementMetier, RegleEvenementComptable,
    OrganisationComptable,
)


class OrganisationComptableSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrganisationComptable
        fields = ["id", "code", "nom", "actif", "metadata"]


class CompteComptableSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompteComptable
        fields = "__all__"


class AffectationAnalytiqueSerializer(serializers.ModelSerializer):
    dimension_code = serializers.CharField(source="dimension.code", read_only=True)
    valeur_code = serializers.CharField(source="valeur.code", read_only=True)
    valeur_libelle = serializers.CharField(source="valeur.libelle", read_only=True)

    class Meta:
        model = AffectationAnalytique
        fields = [
            "id", "dimension", "dimension_code", "valeur", "valeur_code",
            "valeur_libelle", "pourcentage", "metadata",
        ]
        read_only_fields = ["id", "dimension_code", "valeur_code", "valeur_libelle"]


class LigneEcritureComptableSerializer(serializers.ModelSerializer):
    compte_code = serializers.CharField(source="compte.code", read_only=True)
    compte_libelle = serializers.CharField(source="compte.libelle", read_only=True)
    affectations_analytiques = AffectationAnalytiqueSerializer(many=True, read_only=True)
    dimensions = serializers.JSONField(write_only=True, required=False)

    class Meta:
        model = LigneEcritureComptable
        fields = [
            "id", "compte", "compte_code", "compte_libelle", "libelle",
            "debit", "credit", "affectations_analytiques", "dimensions",
        ]


class EcritureComptableSerializer(serializers.ModelSerializer):
    lignes = LigneEcritureComptableSerializer(many=True, read_only=True)
    total_debit = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    total_credit = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)

    class Meta:
        model = EcritureComptable
        fields = "__all__"
        read_only_fields = [
            "entreprise_id", "validee", "date_validation", "validated_by",
            "created_at", "created_by", "reversal_of", "idempotency_key",
            "source_system", "source_type", "source_id", "source_reference",
        ]


class EcritureCreateSerializer(serializers.ModelSerializer):
    lignes = LigneEcritureComptableSerializer(many=True)

    class Meta:
        model = EcritureComptable
        fields = "__all__"
        read_only_fields = [
            "entreprise_id", "created_at", "created_by", "validated_by",
            "date_validation", "reversal_of", "validee",
        ]

    def create(self, validated_data):
        lignes = validated_data.pop("lignes")
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return EcritureService.creer_ecriture(
            reference=validated_data["reference"],
            date_ecriture=validated_data["date_ecriture"],
            libelle=validated_data["libelle"],
            journal=validated_data["journal"],
            lignes=lignes,
            exercice=validated_data.get("exercice"),
            piece=validated_data.get("piece"),
            validee=False,
            user=user,
            entreprise_id=str(getattr(user, "entreprise_id", "") or ""),
            source_system=validated_data.get("source_system", ""),
            source_type=validated_data.get("source_type", ""),
            source_id=validated_data.get("source_id", ""),
            source_reference=validated_data.get("source_reference", ""),
            idempotency_key=validated_data.get("idempotency_key"),
            metadata=validated_data.get("metadata") or {},
        )

    def validate(self, data):
        """Valide les invariants simples avant le service de domaine."""
        lignes = data.get("lignes", [])
        total_debit = sum((Decimal(str(l.get("debit", 0) or 0)) for l in lignes), Decimal("0.00"))
        total_credit = sum((Decimal(str(l.get("credit", 0) or 0)) for l in lignes), Decimal("0.00"))
        if total_debit != total_credit:
            raise serializers.ValidationError(
                f"L'écriture n'est pas équilibrée : débit={total_debit}, crédit={total_credit}"
            )
        if total_debit == 0:
            raise serializers.ValidationError("Une écriture sans montant est interdite.")
        return data


class JournalComptableSerializer(serializers.ModelSerializer):
    class Meta:
        model = JournalComptable
        fields = "__all__"


class ExerciceComptableSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExerciceComptable
        fields = "__all__"


class ConfigurationComptableSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfigurationComptable
        fields = "__all__"


class PlanAmortissementSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlanAmortissement
        fields = "__all__"


class ImmobilisationSerializer(serializers.ModelSerializer):
    plan_amortissement = PlanAmortissementSerializer(many=True, read_only=True)

    class Meta:
        model = Immobilisation
        fields = "__all__"



class DimensionAnalytiqueSerializer(serializers.ModelSerializer):
    class Meta:
        model = DimensionAnalytique
        fields = "__all__"
        read_only_fields = ["entreprise_id"]


class ValeurAnalytiqueSerializer(serializers.ModelSerializer):
    dimension_code = serializers.CharField(source="dimension.code", read_only=True)

    class Meta:
        model = ValeurAnalytique
        fields = "__all__"


class RegleEvenementComptableSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegleEvenementComptable
        fields = "__all__"
        read_only_fields = ["entreprise_id"]


class EvenementMetierSerializer(serializers.ModelSerializer):
    class Meta:
        model = EvenementMetier
        fields = "__all__"
        read_only_fields = [
            "entreprise_id", "statut", "ecriture", "erreur",
            "created_at", "processed_at",
        ]


class EvenementIngestSerializer(serializers.Serializer):
    type_evenement = serializers.CharField(max_length=100)
    source_system = serializers.CharField(max_length=100)
    source_type = serializers.CharField(max_length=100, required=False, allow_blank=True)
    source_id = serializers.CharField(max_length=255, required=False, allow_blank=True)
    idempotency_key = serializers.CharField(max_length=255)
    payload = serializers.JSONField(required=False, default=dict)
