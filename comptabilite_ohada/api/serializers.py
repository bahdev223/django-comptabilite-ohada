from decimal import Decimal

from rest_framework import serializers

from ..services.ecriture_service import EcritureService
from ..models import (
    CompteComptable, EcritureComptable, LigneEcritureComptable,
    JournalComptable, ExerciceComptable, ConfigurationComptable,
    Immobilisation, PlanAmortissement,
)


class CompteComptableSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompteComptable
        fields = "__all__"


class LigneEcritureComptableSerializer(serializers.ModelSerializer):
    compte_code = serializers.CharField(source="compte.code", read_only=True)
    compte_libelle = serializers.CharField(source="compte.libelle", read_only=True)

    class Meta:
        model = LigneEcritureComptable
        fields = ["id", "compte", "compte_code", "compte_libelle", "libelle",
                   "debit", "credit"]


class EcritureComptableSerializer(serializers.ModelSerializer):
    lignes = LigneEcritureComptableSerializer(many=True, read_only=True)
    total_debit = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    total_credit = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)

    class Meta:
        model = EcritureComptable
        fields = "__all__"


class EcritureCreateSerializer(serializers.ModelSerializer):
    lignes = LigneEcritureComptableSerializer(many=True)

    class Meta:
        model = EcritureComptable
        fields = "__all__"

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
            validee=validated_data.get("validee", False),
            user=user,
            entreprise_id=validated_data.get("entreprise_id", ""),
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
