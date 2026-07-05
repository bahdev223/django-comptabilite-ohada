from django.contrib import admin

from .models import (
    CompteComptable, EcritureComptable, LigneEcritureComptable,
    JournalComptable, ExerciceComptable, ConfigurationComptable,
    SoldeInitialComptable, Immobilisation, PlanAmortissement,
    ReleveBancaire, LigneReleveBancaire,
)


class LigneEcritureInline(admin.TabularInline):
    model = LigneEcritureComptable
    extra = 2


@admin.register(CompteComptable)
class CompteComptableAdmin(admin.ModelAdmin):
    list_display = ["code", "libelle", "classe", "nature", "type_compte", "actif"]
    list_filter = ["classe", "nature", "type_compte", "actif"]
    search_fields = ["code", "libelle"]
    ordering = ["code"]


@admin.register(EcritureComptable)
class EcritureComptableAdmin(admin.ModelAdmin):
    list_display = ["reference", "date_ecriture", "journal", "exercice", "validee", "createur"]
    list_filter = ["validee", "journal", "type_operation"]
    search_fields = ["reference", "libelle"]
    inlines = [LigneEcritureInline]
    date_hierarchy = "date_ecriture"


@admin.register(JournalComptable)
class JournalComptableAdmin(admin.ModelAdmin):
    list_display = ["code", "libelle", "type_journal", "actif"]
    list_filter = ["type_journal", "actif"]
    search_fields = ["code", "libelle"]


@admin.register(ExerciceComptable)
class ExerciceComptableAdmin(admin.ModelAdmin):
    list_display = ["code", "libelle", "date_debut", "date_fin", "cloture"]
    list_filter = ["cloture"]
    search_fields = ["code", "libelle"]


@admin.register(ConfigurationComptable)
class ConfigurationComptableAdmin(admin.ModelAdmin):
    list_display = ["societe", "journal_vente", "journal_achat", "journal_tresorerie"]


@admin.register(SoldeInitialComptable)
class SoldeInitialComptableAdmin(admin.ModelAdmin):
    list_display = ["compte", "exercice", "debit", "credit"]
    list_filter = ["exercice"]


class PlanAmortissementInline(admin.TabularInline):
    model = PlanAmortissement
    extra = 0
    readonly_fields = ["annee", "annuite", "cumul_amortissement", "valeur_nette_comptable"]


@admin.register(Immobilisation)
class ImmobilisationAdmin(admin.ModelAdmin):
    list_display = ["code", "designation", "valeur_acquisition", "mode_amortissement", "statut"]
    list_filter = ["mode_amortissement", "statut"]
    search_fields = ["code", "designation"]
    inlines = [PlanAmortissementInline]


@admin.register(ReleveBancaire)
class ReleveBancaireAdmin(admin.ModelAdmin):
    list_display = ["compte_bancaire", "date_releve", "solde_comptable", "solde_banque", "rapproche"]
    list_filter = ["rapproche"]


@admin.register(LigneReleveBancaire)
class LigneReleveBancaireAdmin(admin.ModelAdmin):
    list_display = ["releve", "date", "libelle", "montant", "rapproche"]
    list_filter = ["rapproche"]
