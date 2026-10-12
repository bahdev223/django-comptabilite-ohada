from decimal import Decimal

from django.conf import settings
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _


class AccountingQuerySet(models.QuerySet):
    """Accounting mutations must use the locked domain service, never bulk ORM."""

    def update(self, **kwargs):
        from django.core.exceptions import ValidationError
        raise ValidationError('Mutation comptable en masse interdite.')

    def delete(self):
        from django.core.exceptions import ValidationError
        raise ValidationError('Suppression comptable en masse interdite.')

    def bulk_create(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        raise ValidationError('Import comptable direct interdit.')

    def bulk_update(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        raise ValidationError('Mutation comptable en masse interdite.')


class EcritureComptable(models.Model):
    """Écriture comptable en partie double."""

    objects = AccountingQuerySet.as_manager()

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

    @transaction.atomic
    def save(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        from ..tenancy import require_enterprise, require_owned
        require_enterprise(self.entreprise_id)
        from .exercice import ExerciceComptable
        journal = require_owned(self.journal, self.entreprise_id)
        exercise = require_owned(self.exercice, self.entreprise_id)
        exercise = ExerciceComptable.objects.select_for_update().get(pk=exercise.pk)
        self.date_ecriture = self._meta.get_field('date_ecriture').to_python(self.date_ecriture)
        if not journal.actif or exercise.cloture or not exercise.date_debut <= self.date_ecriture <= exercise.date_fin:
            raise ValidationError('Journal inactif, exercice clos ou date hors période.')
        previous = type(self).objects.filter(pk=self.pk).first() if self.pk else None
        if previous:
            raise ValidationError('Mutation directe interdite ; service transactionnel obligatoire.')
        if self.validee:
            raise ValidationError('Validation uniquement via ValidationService.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        raise ValidationError('Suppression directe interdite ; contrepassation obligatoire.')

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

    objects = AccountingQuerySet.as_manager()

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
        from django.core.exceptions import ValidationError
        if self.debit and self.credit:
            raise ValidationError(_("Une ligne ne peut pas avoir débit ET crédit"))
        if self.debit < 0 or self.credit < 0:
            raise ValidationError(_("Les montants doivent être positifs"))

    @transaction.atomic
    def save(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        from ..tenancy import require_owned, money
        from .exercice import ExerciceComptable
        if self.pk:
            raise ValidationError('Mutation directe de ligne interdite.')
        entry = EcritureComptable.objects.get(pk=self.ecriture_id)
        # Same lock order as validation and closure; cannot append after posting.
        exercise = ExerciceComptable.objects.select_for_update().get(pk=entry.exercice_id)
        entry = EcritureComptable.objects.select_for_update().get(pk=entry.pk)
        if entry.validee or exercise.cloture:
            raise ValidationError('Lignes validées ou exercice clos immuables.')
        account = require_owned(self.compte, entry.entreprise_id)
        if not account.actif:
            raise ValidationError('Compte comptable inactif.')
        self.compte = account
        self.debit, self.credit = money(self.debit), money(self.credit)
        if bool(self.debit) == bool(self.credit):
            raise ValidationError('Une seule colonne positive par ligne.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        raise ValidationError('Suppression directe de ligne interdite.')
