from rest_framework import serializers

from ..models import (
    CompteComptable, EcritureComptable, LigneEcritureComptable,
    JournalComptable, ExerciceComptable, ConfigurationComptable,
    Immobilisation, PlanAmortissement,
)


class CompteComptableSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompteComptable
        fields = ['id', 'code', 'libelle', 'nature', 'sens', 'parent', 'niveau', 'type_compte', 'est_mouvement', 'categorie', 'actif', 'entreprise_id']
        read_only_fields = fields


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
        fields = ['id', 'reference', 'date_ecriture', 'libelle', 'journal', 'piece', 'exercice', 'validee', 'date_validation', 'created_at', 'created_by', 'entreprise_id']
        fields += ['lignes', 'total_debit', 'total_credit']
        read_only_fields = fields


class EcritureCreateSerializer(serializers.ModelSerializer):
    lignes = LigneEcritureComptableSerializer(many=True)

    class Meta:
        model = EcritureComptable
        fields = ['id', 'reference', 'date_ecriture', 'libelle', 'journal', 'piece', 'exercice', 'validee', 'date_validation', 'created_at', 'created_by', 'entreprise_id']
        fields += ['lignes']
        read_only_fields = fields

    def create(self, validated_data):
        raise serializers.ValidationError('Saisie historique désactivée ; EcritureService tenant-scoped requis.')

    def update(self, instance, validated_data):
        raise serializers.ValidationError('Mutation directe interdite.')

    def validate(self, data):
        raise serializers.ValidationError('Saisie historique désactivée.')


class JournalComptableSerializer(serializers.ModelSerializer):
    class Meta:
        model = JournalComptable
        fields = ['id', 'code', 'libelle', 'type_journal', 'actif', 'entreprise_id']
        read_only_fields = fields


class ExerciceComptableSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExerciceComptable
        fields = ['id', 'code', 'date_debut', 'date_fin', 'cloture', 'date_cloture', 'created_at', 'entreprise_id']
        read_only_fields = fields


class ConfigurationComptableSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfigurationComptable
        fields = ['id', 'nom', 'devise', 'nif', 'stat', 'rccm', 'exercice', 'est_initialise', 'date_initialisation', 'contrepartie_situation', 'compte_caisse_defaut', 'compte_banque_defaut', 'compte_client_defaut', 'compte_fournisseur_defaut', 'tva_active', 'taux_tva', 'created_at', 'updated_at']
        fields += ['entreprise_id']
        read_only_fields = fields


class PlanAmortissementSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlanAmortissement
        fields = ['id', 'immobilisation', 'periode', 'montant', 'amortissement_cumule', 'valeur_nette', 'ecriture_generee', 'ecriture_reference']
        read_only_fields = fields


class ImmobilisationSerializer(serializers.ModelSerializer):
    plan_amortissement = PlanAmortissementSerializer(many=True, read_only=True)

    class Meta:
        model = Immobilisation
        fields = ['id', 'code', 'libelle', 'type_immobilisation', 'date_acquisition', 'valeur_originale', 'valeur_residuelle', 'duree_ans', 'compte_immobilisation', 'compte_amortissement', 'compte_charge', 'statut', 'notes', 'created_at', 'updated_at']
        fields += ['entreprise_id', 'plan_amortissement']
        read_only_fields = fields

