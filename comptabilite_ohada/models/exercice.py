from django.db import models
from django.utils.translation import gettext_lazy as _


class ExerciceComptable(models.Model):
    """Exercice comptable (période fiscale)."""

    code = models.CharField(_("Code"), max_length=20, unique=True)
    date_debut = models.DateField(_("Date de début"))
    date_fin = models.DateField(_("Date de fin"))
    cloture = models.BooleanField(_("Clôturé"), default=False)
    date_cloture = models.DateField(_("Date de clôture"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Exercice comptable")
        verbose_name_plural = _("Exercices comptables")
        ordering = ["-date_debut"]

    def __str__(self):
        return f"Exercice {self.code} ({self.date_debut} → {self.date_fin})"

    @property
    def est_ouvert(self):
        return not self.cloture
