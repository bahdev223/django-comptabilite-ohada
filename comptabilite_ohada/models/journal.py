from django.db import models
from django.utils.translation import gettext_lazy as _


class JournalComptable(models.Model):
    """Journal comptable (Achats, Ventes, Banque, Caisse, OD)."""

    TYPE_JOURNAL = [
        ("ACHATS", _("Achats")),
        ("VENTES", _("Ventes")),
        ("BANQUE", _("Banque")),
        ("CAISSE", _("Caisse")),
        ("OD", _("Opérations Diverses")),
        ("PAIE", _("Paie")),
        ("STOCK", _("Stock")),
        ("IMMO", _("Immobilisations")),
    ]

    code = models.CharField(_("Code"), max_length=10, unique=True)
    libelle = models.CharField(_("Libellé"), max_length=100)
    type_journal = models.CharField(_("Type"), max_length=20, choices=TYPE_JOURNAL)
    actif = models.BooleanField(_("Actif"), default=True)

    class Meta:
        verbose_name = _("Journal comptable")
        verbose_name_plural = _("Journaux comptables")
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.libelle}"
