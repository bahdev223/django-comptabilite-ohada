from decimal import Decimal
from datetime import date

from django.db import models
from django.utils.translation import gettext_lazy as _


class Immobilisation(models.Model):
    """Immobilisation (actif fixe amortissable)."""

    TYPE_CHOICES = [
        ("CORPORELLE", _("Immobilisation corporelle")),
        ("INCORPORELLE", _("Immobilisation incorporelle")),
        ("FINANCIERE", _("Immobilisation financière")),
    ]

    code = models.CharField(_("Code"), max_length=20, unique=True)
    libelle = models.CharField(_("Libellé"), max_length=200)
    type_immobilisation = models.CharField(
        _("Type"), max_length=20, choices=TYPE_CHOICES,
    )
    date_acquisition = models.DateField(_("Date d'acquisition"))
    valeur_originale = models.DecimalField(_("Valeur d'origine"), max_digits=15, decimal_places=2)
    valeur_residuelle = models.DecimalField(_("Valeur résiduelle"), max_digits=15, decimal_places=2, default=0)
    duree_ans = models.IntegerField(_("Durée (années)"))

    compte_immobilisation = models.ForeignKey(
        "CompteComptable", on_delete=models.PROTECT,
        related_name="immobilisations", verbose_name=_("Compte immobilisation"),
    )
    compte_amortissement = models.ForeignKey(
        "CompteComptable", on_delete=models.PROTECT,
        related_name="amortissements", verbose_name=_("Compte amortissement"),
    )
    compte_charge = models.ForeignKey(
        "CompteComptable", on_delete=models.PROTECT,
        related_name="charges_amortissement", verbose_name=_("Compte charge"),
    )

    statut = models.CharField(
        _("Statut"), max_length=20, default="ACTIF",
        choices=[("ACTIF", "Actif"), ("CESSION", "Cédé"), ("SORTIE", "Sorti")],
    )
    notes = models.TextField(_("Notes"), blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Immobilisation")
        verbose_name_plural = _("Immobilisations")
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.libelle}"

    @property
    def base_amortissable(self):
        return self.valeur_originale - self.valeur_residuelle

    @property
    def amortissement_annuel(self):
        if self.duree_ans > 0:
            return self.base_amortissable / self.duree_ans
        return Decimal("0.00")

    @property
    def amortissement_mensuel(self):
        return self.amortissement_annuel / 12

    def calculer_amortissements_cumules(self, date_fin=None):
        if date_fin is None:
            date_fin = date.today()
        mois = (date_fin.year - self.date_acquisition.year) * 12 \
             + (date_fin.month - self.date_acquisition.month)
        if mois < 0:
            return Decimal("0.00")
        return self.amortissement_mensuel * min(mois, self.duree_ans * 12)

    def valeur_nette_comptable(self, date_fin=None):
        return self.valeur_originale - self.calculer_amortissements_cumules(date_fin)


class PlanAmortissement(models.Model):
    """Échéancier d'amortissement."""

    immobilisation = models.ForeignKey(
        Immobilisation, on_delete=models.CASCADE, related_name="plan_amortissement",
    )
    periode = models.DateField(_("Période"))
    montant = models.DecimalField(_("Montant"), max_digits=15, decimal_places=2)
    amortissement_cumule = models.DecimalField(_("Amorti cumulé"), max_digits=15, decimal_places=2)
    valeur_nette = models.DecimalField(_("Valeur nette"), max_digits=15, decimal_places=2)
    ecriture_generee = models.BooleanField(_("Écriture générée"), default=False)
    ecriture_reference = models.CharField(_("Réf. écriture"), max_length=50, blank=True, null=True)

    class Meta:
        verbose_name = _("Plan d'amortissement")
        verbose_name_plural = _("Plans d'amortissement")
        ordering = ["periode"]
        unique_together = ["immobilisation", "periode"]

    def __str__(self):
        return f"{self.immobilisation.code} - {self.periode.strftime('%m/%Y')}"
