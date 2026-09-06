from django.contrib import admin

from .models import (
    CompteComptable,
    ConfigurationComptable,
    EcritureComptable,
    ExerciceComptable,
    Immobilisation,
    JournalComptable,
    LigneEcritureComptable,
    LigneReleveBancaire,
    PlanAmortissement,
    ReleveBancaire,
    SoldeInitialComptable,
)


@admin.register(CompteComptable)
class CompteComptableAdmin(admin.ModelAdmin):
    list_display = ("code", "libelle", "nature", "niveau", "actif")
    list_filter = ("nature", "niveau", "actif")
    search_fields = ("code", "libelle")


@admin.register(JournalComptable)
class JournalComptableAdmin(admin.ModelAdmin):
    list_display = ("code", "libelle", "type_journal", "actif")
    list_filter = ("type_journal", "actif")
    search_fields = ("code", "libelle")


@admin.register(ExerciceComptable)
class ExerciceComptableAdmin(admin.ModelAdmin):
    list_display = ("code", "date_debut", "date_fin", "cloture")
    list_filter = ("cloture",)


@admin.register(EcritureComptable)
class EcritureComptableAdmin(admin.ModelAdmin):
    list_display = ("reference", "date_ecriture", "journal", "exercice", "validee")
    list_filter = ("journal", "exercice", "validee")
    search_fields = ("reference", "libelle")


admin.site.register(LigneEcritureComptable)
admin.site.register(ConfigurationComptable)
admin.site.register(SoldeInitialComptable)
admin.site.register(Immobilisation)
admin.site.register(PlanAmortissement)
admin.site.register(ReleveBancaire)
admin.site.register(LigneReleveBancaire)
