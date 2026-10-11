from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from ..tenancy import require_tenant, check_owned, is_ledger_validation_allowed


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

    # Preparation multi-entreprises. Vide tant que l'application ne sert
    # qu'une entreprise ; le projet hote y place l'identifiant de son
    # organisation le jour ou il en gere plusieurs. Un CharField plutot
    # qu'une cle etrangere : le paquet reste ainsi utilisable sans
    # connaitre le modele d'organisation de l'hote.
    entreprise_id = models.CharField(max_length=255, blank=True, default="", db_index=True)

    class Meta:
        # Unicite par entreprise plutot que globale : deux entreprises
        # doivent pouvoir employer le meme reference.
        unique_together = [["entreprise_id", "reference"]]
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

    def clean(self):
        super().clean()
        tenant = require_tenant(self.entreprise_id)
        if self.journal_id:
            check_owned(self.journal, tenant, what="Journal")
            if not self.journal.actif:
                raise ValidationError("Journal inactif.")
        if self.exercice_id:
            check_owned(self.exercice, tenant, what="Exercice")
            day = self.date_ecriture
            if isinstance(day, str):
                from datetime import date
                try:
                    day = date.fromisoformat(day)
                except ValueError as exc:
                    raise ValidationError("Date d'écriture invalide.") from exc
            # Reload typed dates from DB; freshly constructed FK instances
            # may still contain ISO strings before Django field conversion.
            exercice = self.exercice.__class__.objects.get(pk=self.exercice_id)
            check_owned(exercice, tenant, what="Exercice")
            if not exercice.date_debut <= day <= exercice.date_fin:
                raise ValidationError("Écriture datée hors exercice.")
            if exercice.cloture:
                raise ValidationError("Une écriture ne peut pas être modifiée dans un exercice clôturé.")

    def save(self, *args, **kwargs):
        if not self.entreprise_id:
            if self.pk is not None:
                raise ValidationError(
                    "Enregistrement historique sans entreprise : reprise auditée obligatoire."
                )
            self.entreprise_id = require_tenant()
        else:
            require_tenant(self.entreprise_id)
        # No ORM insert of a pre-validated empty entry. Only ValidationService
        # may perform the transition from draft to validated.
        if self.pk is None and self.validee:
            raise ValidationError("Créer d'abord le brouillon et ses lignes.")
        if self.pk is not None:
            previous = type(self).objects.filter(pk=self.pk).first()
            if previous is not None:
                if previous.validee:
                    raise ValidationError("Une écriture validée est immuable.")
                if self.validee and not is_ledger_validation_allowed():
                    raise ValidationError("La validation exige ValidationService.")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.validee:
            raise ValidationError("Une écriture validée ne peut être supprimée.")
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


class LigneEcritureComptable(models.Model):
    """Ligne d'une écriture comptable."""

    ecriture = models.ForeignKey(
        EcritureComptable, on_delete=models.PROTECT, related_name="lignes",
        verbose_name=_("Écriture"),
    )
    compte = models.ForeignKey(
        "CompteComptable", on_delete=models.PROTECT, verbose_name=_("Compte"),
    )
    debit = models.DecimalField(_("Débit"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    credit = models.DecimalField(_("Crédit"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    libelle = models.CharField(_("Libellé ligne"), max_length=200, blank=True, null=True)

    class Meta:
        verbose_name = _("Ligne d'écriture")
        verbose_name_plural = _("Lignes d'écritures")
        indexes = [
            models.Index(fields=["compte"]),
        ]

    def __str__(self):
        return f"{self.ecriture.reference} - {self.compte.code} - {self.debit or self.credit:,.0f}"

    def clean(self):
        super().clean()
        if not self.ecriture_id or not self.compte_id:
            raise ValidationError("Écriture et compte obligatoires.")
        tenant = require_tenant(self.ecriture.entreprise_id)
        check_owned(self.compte, tenant, what="Compte de ligne")
        if not self.compte.actif or not self.compte.est_mouvement:
            raise ValidationError("Compte inactif ou non mouvementable.")
        if self.debit is None or self.credit is None:
            raise ValidationError("Montants obligatoires.")
        from decimal import Decimal
        try:
            debit = Decimal(str(self.debit))
            credit = Decimal(str(self.credit))
        except Exception as exc:
            raise ValidationError("Montant invalide.") from exc
        if not debit.is_finite() or not credit.is_finite():
            raise ValidationError("Montants non finis interdits.")
        if debit < 0 or credit < 0 or (debit > 0) == (credit > 0):
            raise ValidationError("Chaque ligne a un seul sens strictement positif.")
        if self.ecriture.validee:
            raise ValidationError("Les lignes d'une écriture validée sont immuables.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.ecriture.validee:
            raise ValidationError("Les lignes validées ne peuvent être supprimées.")
        return super().delete(*args, **kwargs)
