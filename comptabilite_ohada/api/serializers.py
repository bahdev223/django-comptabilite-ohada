"""Explicit API fields. Never expose tenant fields as writable ModelSerializer."""
from decimal import Decimal

from rest_framework import serializers

from ..models import (
    CompteComptable, EcritureComptable, JournalComptable,
    ExerciceComptable, ConfigurationComptable, Immobilisation,
    PlanAmortissement,
)


class CompteComptableSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompteComptable
        fields = (
            "id", "code", "libelle", "nature", "sens", "parent", "niveau",
            "type_compte", "est_mouvement", "categorie", "actif",
        )
        read_only_fields = fields


class JournalComptableSerializer(serializers.ModelSerializer):
    class Meta:
        model = JournalComptable
        fields = ("id", "code", "libelle", "type_journal", "actif")
        read_only_fields = fields


class ExerciceComptableSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExerciceComptable
        fields = ("id", "code", "date_debut", "date_fin", "cloture", "date_cloture")
        read_only_fields = fields


class LigneEcritureComptableSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    compte = serializers.IntegerField(read_only=True, source="compte_id")
    compte_code = serializers.CharField(source="compte.code", read_only=True)
    compte_libelle = serializers.CharField(source="compte.libelle", read_only=True)
    libelle = serializers.CharField(read_only=True)
    debit = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    credit = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)


class EcritureComptableSerializer(serializers.ModelSerializer):
    lignes = serializers.SerializerMethodField()
    total_debit = serializers.SerializerMethodField()
    total_credit = serializers.SerializerMethodField()

    class Meta:
        model = EcritureComptable
        fields = (
            "id", "reference", "date_ecriture", "libelle", "journal",
            "exercice", "piece", "validee", "date_validation",
            "created_at", "created_by", "lignes", "total_debit", "total_credit",
        )
        read_only_fields = fields

    def _lignes(self, obj):
        tenant = self.context.get("tenant_id")
        if not tenant:
            return obj.lignes.none()
        return obj.lignes.filter(
            ecriture__entreprise_id=tenant,
            compte__entreprise_id=tenant,
        ).select_related("compte")

    def get_lignes(self, obj):
        return LigneEcritureComptableSerializer(self._lignes(obj), many=True).data

    def get_total_debit(self, obj):
        return sum((line.debit for line in self._lignes(obj)), Decimal("0.00"))

    def get_total_credit(self, obj):
        return sum((line.credit for line in self._lignes(obj)), Decimal("0.00"))


class LigneEcritureInputSerializer(serializers.Serializer):
    compte = serializers.IntegerField(min_value=1)
    debit = serializers.DecimalField(
        max_digits=15, decimal_places=2, min_value=Decimal("0.00"),
        required=False, default=Decimal("0.00"),
    )
    credit = serializers.DecimalField(
        max_digits=15, decimal_places=2, min_value=Decimal("0.00"),
        required=False, default=Decimal("0.00"),
    )
    libelle = serializers.CharField(max_length=200, required=False, allow_blank=True)

    def validate(self, attrs):
        debit, credit = attrs["debit"], attrs["credit"]
        if (debit > 0) == (credit > 0):
            raise serializers.ValidationError("Une ligne comporte un seul montant positif.")
        return attrs


class EcritureCreateSerializer(serializers.Serializer):
    reference = serializers.CharField(max_length=50)
    date_ecriture = serializers.DateField()
    libelle = serializers.CharField(max_length=1000)
    journal = serializers.IntegerField(min_value=1)
    exercice = serializers.IntegerField(min_value=1, required=False)
    piece = serializers.CharField(
        max_length=50, required=False, allow_blank=True, allow_null=True,
    )
    lignes = LigneEcritureInputSerializer(many=True, allow_empty=False)

    def validate(self, attrs):
        lines = attrs["lignes"]
        if len(lines) < 2:
            raise serializers.ValidationError("Deux lignes comptables minimum.")
        debit = sum((item["debit"] for item in lines), Decimal("0.00"))
        credit = sum((item["credit"] for item in lines), Decimal("0.00"))
        if debit != credit or debit <= 0:
            raise serializers.ValidationError("Écriture déséquilibrée ou vide.")
        return attrs

    def create(self, validated_data):
        # All writes MUST go via EcritureService with trusted tenant context.
        raise NotImplementedError("Création directe de ModelSerializer interdite.")
