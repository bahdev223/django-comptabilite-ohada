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
    DimensionAnalytique,
    ValeurAnalytique,
    AffectationAnalytique,
    EvenementMetier,
    RegleEvenementComptable,
    OrganisationComptable,
    AccesEntrepriseComptable,
    ApplicationClienteComptable,
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

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.validee:
            return False
        return super().has_delete_permission(request, obj)

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions


admin.site.register(LigneEcritureComptable)
admin.site.register(ConfigurationComptable)
admin.site.register(SoldeInitialComptable)
admin.site.register(Immobilisation)
admin.site.register(PlanAmortissement)
admin.site.register(ReleveBancaire)
admin.site.register(LigneReleveBancaire)



@admin.register(DimensionAnalytique)
class DimensionAnalytiqueAdmin(admin.ModelAdmin):
    list_display = ("entreprise_id", "code", "libelle", "actif")
    list_filter = ("actif", "entreprise_id")
    search_fields = ("code", "libelle")


@admin.register(ValeurAnalytique)
class ValeurAnalytiqueAdmin(admin.ModelAdmin):
    list_display = ("dimension", "code", "libelle", "external_id", "actif")
    list_filter = ("actif", "dimension")
    search_fields = ("code", "libelle", "external_id")


@admin.register(EvenementMetier)
class EvenementMetierAdmin(admin.ModelAdmin):
    list_display = (
        "type_evenement", "source_system", "source_id", "statut",
        "entreprise_id", "created_at",
    )
    list_filter = ("statut", "type_evenement", "source_system", "entreprise_id")
    search_fields = ("idempotency_key", "source_id", "source_system")


@admin.register(RegleEvenementComptable)
class RegleEvenementComptableAdmin(admin.ModelAdmin):
    list_display = ("type_evenement", "code_regle", "entreprise_id", "actif")
    list_filter = ("actif", "entreprise_id")
    search_fields = ("type_evenement", "code_regle")


admin.site.register(AffectationAnalytique)


@admin.register(OrganisationComptable)
class OrganisationComptableAdmin(admin.ModelAdmin):
    list_display = ("code", "nom", "actif", "created_at")
    list_filter = ("actif",)
    search_fields = ("code", "nom")


@admin.register(AccesEntrepriseComptable)
class AccesEntrepriseComptableAdmin(admin.ModelAdmin):
    list_display = ("user", "entreprise", "role", "actif")
    list_filter = ("role", "actif", "entreprise")
    search_fields = ("user__username", "entreprise__code", "entreprise__nom")



@admin.register(ApplicationClienteComptable)
class ApplicationClienteComptableAdmin(admin.ModelAdmin):
    list_display = (
        "nom", "entreprise", "prefixe", "actif", "last_used_at", "created_at",
    )
    list_filter = ("actif", "entreprise")
    search_fields = ("nom", "prefixe", "entreprise__code")
    readonly_fields = ("prefixe", "secret_hash", "last_used_at", "created_at")

    def has_add_permission(self, request):
        # La création passe par creer_cle_api afin que le secret brut soit
        # affiché exactement une fois.
        return False
