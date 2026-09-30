from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class OrganisationComptable(models.Model):
    """Registre local optionnel des entreprises pour le mode standalone."""

    code = models.CharField(max_length=100, unique=True)
    nom = models.CharField(max_length=200)
    actif = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nom"]
        verbose_name = _("Organisation comptable")
        verbose_name_plural = _("Organisations comptables")

    def __str__(self):
        return f"{self.code} - {self.nom}"


class AccesEntrepriseComptable(models.Model):
    """Droit d'un utilisateur local sur une entreprise comptable."""

    ROLES = [
        ("ADMIN", _("Administrateur")),
        ("COMPTABLE", _("Comptable")),
        ("VALIDATEUR", _("Validateur")),
        ("LECTURE", _("Lecture seule")),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="acces_comptables",
    )
    entreprise = models.ForeignKey(
        OrganisationComptable,
        on_delete=models.CASCADE,
        related_name="acces_utilisateurs",
    )
    role = models.CharField(max_length=20, choices=ROLES, default="LECTURE")
    actif = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = [["user", "entreprise"]]
        verbose_name = _("Accès entreprise comptable")
        verbose_name_plural = _("Accès entreprises comptables")

    def __str__(self):
        return f"{self.user} -> {self.entreprise.code} ({self.role})"
