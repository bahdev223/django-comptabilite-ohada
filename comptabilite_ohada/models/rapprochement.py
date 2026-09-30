from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


class ReleveBancaire(models.Model):
    """Relevé bancaire importé pour rapprochement."""

    STATUT_CHOICES = [
        ("BROUILLON", _("Brouillon")),
        ("EN_COURS", _("En cours")),
        ("RAPPROCHE", _("Rapproché")),
    ]

    entreprise_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
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

    def clean(self):
        if self.date_debut and self.date_fin and self.date_fin < self.date_debut:
            raise ValidationError("La date de fin du relevé précède la date de début.")
        from .compte import CompteComptable
        if self.compte_comptable_code:
            compte = CompteComptable.objects.filter(
                entreprise_id=self.entreprise_id or "",
                code=self.compte_comptable_code,
                actif=True,
            ).first()
            if compte is None or not compte.code.startswith("5"):
                raise ValidationError(
                    "Le compte bancaire doit être un compte de trésorerie actif de l'entreprise."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


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

    def clean(self):
        if self.montant <= 0:
            raise ValidationError("Le montant d'une ligne de relevé doit être positif.")

    def save(self, *args, **kwargs):
        if self.releve_id and self.releve.statut == "RAPPROCHE":
            raise ValidationError("Un relevé rapproché est verrouillé.")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.releve.statut == "RAPPROCHE":
            raise ValidationError("Un relevé rapproché est verrouillé.")
        return super().delete(*args, **kwargs)
