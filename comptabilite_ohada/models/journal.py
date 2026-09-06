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

    code = models.CharField(_("Code"), max_length=10)
    libelle = models.CharField(_("Libellé"), max_length=100)
    type_journal = models.CharField(_("Type"), max_length=20, choices=TYPE_JOURNAL)
    actif = models.BooleanField(_("Actif"), default=True)

    # Preparation multi-entreprises. Vide tant que l'application ne sert
    # qu'une entreprise ; le projet hote y place l'identifiant de son
    # organisation le jour ou il en gere plusieurs. Un CharField plutot
    # qu'une cle etrangere : le paquet reste ainsi utilisable sans
    # connaitre le modele d'organisation de l'hote.
    entreprise_id = models.CharField(max_length=255, blank=True, default="", db_index=True)

    class Meta:
        # Unicite par entreprise plutot que globale : deux entreprises
        # doivent pouvoir employer le meme code.
        unique_together = [["entreprise_id", "code"]]
        verbose_name = _("Journal comptable")
        verbose_name_plural = _("Journaux comptables")
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.libelle}"
