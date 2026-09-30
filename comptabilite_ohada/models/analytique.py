from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


class DimensionAnalytique(models.Model):
    """Axe analytique générique : projet, phase, mission, site, centre de coût, etc."""

    entreprise_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    code = models.CharField(max_length=50)
    libelle = models.CharField(max_length=150)
    actif = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = [["entreprise_id", "code"]]
        ordering = ["code"]
        verbose_name = _("Dimension analytique")
        verbose_name_plural = _("Dimensions analytiques")

    def __str__(self):
        return f"{self.code} - {self.libelle}"


class ValeurAnalytique(models.Model):
    """Valeur d'un axe analytique, référencée sans dépendre du modèle métier source."""

    dimension = models.ForeignKey(
        DimensionAnalytique, on_delete=models.CASCADE, related_name="valeurs"
    )
    code = models.CharField(max_length=100)
    libelle = models.CharField(max_length=200)
    external_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    actif = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = [["dimension", "code"]]
        ordering = ["dimension__code", "code"]
        verbose_name = _("Valeur analytique")
        verbose_name_plural = _("Valeurs analytiques")

    def __str__(self):
        return f"{self.dimension.code}:{self.code} - {self.libelle}"


class AffectationAnalytique(models.Model):
    """Affecte une ligne comptable à une valeur analytique d'un axe."""

    ligne = models.ForeignKey(
        "LigneEcritureComptable", on_delete=models.CASCADE, related_name="affectations_analytiques"
    )
    dimension = models.ForeignKey(
        DimensionAnalytique, on_delete=models.PROTECT, related_name="affectations"
    )
    valeur = models.ForeignKey(
        ValeurAnalytique, on_delete=models.PROTECT, related_name="affectations"
    )
    pourcentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("100.00")
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = [["ligne", "dimension"]]
        verbose_name = _("Affectation analytique")
        verbose_name_plural = _("Affectations analytiques")

    def clean(self):
        if self.valeur.dimension_id != self.dimension_id:
            raise ValidationError("La valeur analytique n'appartient pas à la dimension indiquée.")
        if self.pourcentage <= 0 or self.pourcentage > 100:
            raise ValidationError("Le pourcentage analytique doit être compris entre 0 et 100.")

    def __str__(self):
        return f"{self.ligne_id} - {self.dimension.code}:{self.valeur.code}"
