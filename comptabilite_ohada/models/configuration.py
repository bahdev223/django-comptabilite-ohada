from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _


class ConfigurationComptable(models.Model):
    """Configuration générale de la comptabilité."""

    nom = models.CharField(_("Nom"), max_length=200, default="Mon Entreprise")
    devise = models.CharField(_("Devise"), max_length=10, default="FCFA")

    nif = models.CharField(_("NIF"), max_length=50, blank=True, null=True)
    stat = models.CharField(_("STAT"), max_length=50, blank=True, null=True)
    rccm = models.CharField(_("RCCM"), max_length=50, blank=True, null=True)

    exercice = models.ForeignKey(
        "ExerciceComptable", on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name=_("Exercice en cours"),
    )

    est_initialise = models.BooleanField(_("Initialisé"), default=False)
    date_initialisation = models.DateField(_("Date d'initialisation"), null=True, blank=True)
    contrepartie_situation = models.CharField(
        _("Compte de contrepartie"), max_length=20, default="101"
    )

    compte_caisse_defaut = models.CharField(_("Compte caisse défaut"), max_length=20, default="571")
    compte_banque_defaut = models.CharField(_("Compte banque défaut"), max_length=20, default="521")
    compte_client_defaut = models.CharField(_("Compte client défaut"), max_length=20, default="411")
    compte_fournisseur_defaut = models.CharField(_("Compte fournisseur défaut"), max_length=20, default="401")

    tva_active = models.BooleanField(_("TVA active"), default=True)
    taux_tva = models.DecimalField(_("Taux TVA %"), max_digits=5, decimal_places=2, default=Decimal("18.00"))

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Configuration comptable")
        verbose_name_plural = _("Configuration comptable")

    def __str__(self):
        return self.nom

    @classmethod
    def get_config(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class SoldeInitialComptable(models.Model):
    """Soldes initiaux pour l'initialisation comptable."""

    configuration = models.OneToOneField(
        ConfigurationComptable, on_delete=models.CASCADE,
        related_name="soldes_initiaux",
    )

    caisse = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    banque = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    stocks = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    clients = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    fournisseurs = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    capital_social = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    class Meta:
        verbose_name = _("Solde initial")
        verbose_name_plural = _("Soldes initiaux")

    def __str__(self):
        return f"Soldes initiaux — {self.configuration.nom}"
