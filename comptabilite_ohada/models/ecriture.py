from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


class EcritureComptableQuerySet(models.QuerySet):
    def delete(self):
        if self.filter(validee=True).exists():
            raise ValidationError(
                "Une écriture validée ne peut pas être supprimée. Utilisez une contre-passation."
            )
        return super().delete()


class EcritureComptable(models.Model):
    """Écriture comptable en partie double."""

    reference = models.CharField(_("Référence"), max_length=50)
    date_ecriture = models.DateField(_("Date d'écriture"))
    libelle = models.TextField(_("Libellé"))
    journal = models.ForeignKey(
        "JournalComptable", on_delete=models.PROTECT, verbose_name=_("Journal"),
    )
    piece = models.CharField(_("Pièce"), max_length=50, blank=True, null=True)
    exercice = models.ForeignKey(
        "ExerciceComptable", on_delete=models.PROTECT, verbose_name=_("Exercice"),
    )
    validee = models.BooleanField(_("Validée"), default=False)
    date_validation = models.DateTimeField(_("Date validation"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.CharField(_("Créé par"), max_length=100, blank=True, null=True)
    validated_by = models.CharField(_("Validé par"), max_length=100, blank=True, null=True)

    source_system = models.CharField(max_length=100, blank=True, default="", db_index=True)
    source_type = models.CharField(max_length=100, blank=True, default="")
    source_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    source_reference = models.CharField(max_length=255, blank=True, default="")
    idempotency_key = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    reversal_of = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True,
        related_name="reversals", verbose_name=_("Contre-passation de"),
    )

    # Preparation multi-entreprises. Vide tant que l'application ne sert
    # qu'une entreprise ; le projet hote y place l'identifiant de son
    # organisation le jour ou il en gere plusieurs. Un CharField plutot
    # qu'une cle etrangere : le paquet reste ainsi utilisable sans
    # connaitre le modele d'organisation de l'hote.
    entreprise_id = models.CharField(max_length=255, blank=True, default="", db_index=True)

    objects = EcritureComptableQuerySet.as_manager()

    class Meta:
        # Unicite par entreprise plutot que globale : deux entreprises
        # doivent pouvoir employer le meme reference.
        unique_together = [["entreprise_id", "reference"]]
        constraints = [
            models.UniqueConstraint(
                fields=["entreprise_id", "idempotency_key"],
                condition=models.Q(idempotency_key__isnull=False),
                name="uniq_ecriture_idempotente_par_entreprise",
            )
        ]
        verbose_name = _("Écriture comptable")
        verbose_name_plural = _("Écritures comptables")
        ordering = ["-date_ecriture", "-created_at"]
        indexes = [
            models.Index(fields=["reference"]),
            models.Index(fields=["date_ecriture"]),
            models.Index(fields=["journal", "date_ecriture"]),
        ]

    def __str__(self):
        return f"{self.reference} - {self.date_ecriture} - {self.libelle[:60]}"

    def save(self, *args, **kwargs):
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).values("validee").first()
            if previous and previous["validee"]:
                raise ValidationError(
                    "Une écriture validée est immuable. Utilisez une contre-passation."
                )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.validee:
            raise ValidationError(
                "Une écriture validée ne peut pas être supprimée. Utilisez une contre-passation."
            )
        return super().delete(*args, **kwargs)

    @property
    def total_debit(self):
        return self.lignes.aggregate(total=models.Sum("debit"))["total"] or Decimal("0.00")

    @property
    def total_credit(self):
        return self.lignes.aggregate(total=models.Sum("credit"))["total"] or Decimal("0.00")

    @property
    def est_equilibree(self):
        return self.total_debit == self.total_credit


class LigneEcritureQuerySet(models.QuerySet):
    def delete(self):
        if self.filter(ecriture__validee=True).exists():
            raise ValidationError(
                "Les lignes d'une écriture validée ne peuvent pas être supprimées."
            )
        return super().delete()


class LigneEcritureComptable(models.Model):
    """Ligne d'une écriture comptable."""

    ecriture = models.ForeignKey(
        EcritureComptable, on_delete=models.CASCADE, related_name="lignes",
        verbose_name=_("Écriture"),
    )
    compte = models.ForeignKey(
        "CompteComptable", on_delete=models.PROTECT, verbose_name=_("Compte"),
    )
    debit = models.DecimalField(_("Débit"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    credit = models.DecimalField(_("Crédit"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    libelle = models.CharField(_("Libellé ligne"), max_length=200, blank=True, null=True)

    objects = LigneEcritureQuerySet.as_manager()

    class Meta:
        verbose_name = _("Ligne d'écriture")
        verbose_name_plural = _("Lignes d'écritures")
        indexes = [
            models.Index(fields=["compte"]),
        ]

    def __str__(self):
        return f"{self.ecriture.reference} - {self.compte.code} - {self.debit or self.credit:,.0f}"

    def save(self, *args, **kwargs):
        if self.ecriture_id and self.ecriture.validee:
            raise ValidationError(
                "Les lignes d'une écriture validée sont immuables."
            )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.ecriture.validee:
            raise ValidationError(
                "Les lignes d'une écriture validée ne peuvent pas être supprimées."
            )
        return super().delete(*args, **kwargs)

    def clean(self):
        if self.debit and self.credit:
            raise ValidationError(_("Une ligne ne peut pas avoir débit ET crédit"))
        if self.debit < 0 or self.credit < 0:
            raise ValidationError(_("Les montants doivent être positifs"))
