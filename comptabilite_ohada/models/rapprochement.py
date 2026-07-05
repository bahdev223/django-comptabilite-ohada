from django.db import models
from django.utils.translation import gettext_lazy as _


class ReleveBancaire(models.Model):
    """Relevé bancaire importé pour rapprochement."""

    STATUT_CHOICES = [
        ("BROUILLON", _("Brouillon")),
        ("EN_COURS", _("En cours")),
        ("RAPPROCHE", _("Rapproché")),
    ]

    compte_comptable_code = models.CharField(
        _("Code compte bancaire"), max_length=20,
        help_text="Code SYSCOHADA du compte banque (521...)",
    )
    date_debut = models.DateField(_("Date début"))
    date_fin = models.DateField(_("Date fin"))
    solde_ouverture = models.DecimalField(_("Solde d'ouverture"), max_digits=15, decimal_places=2)
    solde_cloture = models.DecimalField(_("Solde de clôture"), max_digits=15, decimal_places=2)
    statut = models.CharField(_("Statut"), max_length=20, choices=STATUT_CHOICES, default="BROUILLON")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Relevé bancaire")
        verbose_name_plural = _("Relevés bancaires")
        ordering = ["-date_fin"]

    def __str__(self):
        return f"Relevé {self.compte_comptable_code} — {self.date_debut} → {self.date_fin}"


class LigneReleveBancaire(models.Model):
    """Ligne d'un relevé bancaire."""

    SENS_CHOICES = [
        ("CREDIT", _("Crédit (entrée)")),
        ("DEBIT", _("Débit (sortie)")),
    ]

    releve = models.ForeignKey(
        ReleveBancaire, on_delete=models.CASCADE, related_name="lignes",
    )
    date_operation = models.DateField(_("Date"))
    libelle = models.CharField(_("Libellé"), max_length=200)
    montant = models.DecimalField(_("Montant"), max_digits=15, decimal_places=2)
    sens = models.CharField(_("Sens"), max_length=10, choices=SENS_CHOICES)
    reference = models.CharField(_("Référence"), max_length=100, blank=True, null=True)
    pointe = models.BooleanField(_("Pointé"), default=False)

    class Meta:
        verbose_name = _("Ligne de relevé")
        verbose_name_plural = _("Lignes de relevé")
        ordering = ["date_operation"]

    def __str__(self):
        return f"{self.date_operation} - {self.libelle} - {self.montant:,.0f}"
