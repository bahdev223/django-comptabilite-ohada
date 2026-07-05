from rest_framework import serializers

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
                   "debit", "credit", "sens"]


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
        lignes_data = validated_data.pop("lignes")
        ecriture = EcritureComptable.objects.create(**validated_data)
        for ligne_data in lignes_data:
            LigneEcritureComptable.objects.create(ecriture=ecriture, **ligne_data)
        return ecriture

    def validate(self, data):
        """Vérifie que l'écriture est équilibrée."""
        lignes = data.get("lignes", [])
        total_debit = sum(float(l.get("debit", 0) or 0) for l in lignes)
        total_credit = sum(float(l.get("credit", 0) or 0) for l in lignes)
        if abs(total_debit - total_credit) > 0.01:
            raise serializers.ValidationError(
                "L'écriture n'est pas équilibrée : "
                f"débit={total_debit:.2f}, crédit={total_credit:.2f}"
            )
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
