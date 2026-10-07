from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, F
from django.utils.translation import gettext_lazy as _


class ExerciceComptable(models.Model):
    """Exercice comptable (période fiscale)."""

    code = models.CharField(_("Code"), max_length=20)
    date_debut = models.DateField(_("Date de début"))
    date_fin = models.DateField(_("Date de fin"))
    cloture = models.BooleanField(_("Clôturé"), default=False)
    date_cloture = models.DateField(_("Date de clôture"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

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
        verbose_name = _("Exercice comptable")
        verbose_name_plural = _("Exercices comptables")
        ordering = ["-date_debut"]
        constraints = [
            models.CheckConstraint(
                condition=Q(date_fin__gte=F("date_debut")),
                name="exercice_dates_valides",
            )
        ]

    def __str__(self):
        return f"Exercice {self.code} ({self.date_debut} → {self.date_fin})"

    def clean(self):
        if self.date_debut and self.date_fin and self.date_fin < self.date_debut:
            raise ValidationError("La date de fin doit être postérieure à la date de début.")

        if self.date_debut and self.date_fin:
            chevauchement = type(self).objects.filter(
                entreprise_id=self.entreprise_id or "",
                date_debut__lte=self.date_fin,
                date_fin__gte=self.date_debut,
            ).exclude(pk=self.pk)
            if chevauchement.exists():
                raise ValidationError(
                    "Un autre exercice comptable chevauche déjà cette période pour cette entreprise."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def est_ouvert(self):
        return not self.cloture
