from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


class NatureCompte(models.TextChoices):
    ACTIF = "ACTIF", _("Actif")
    PASSIF = "PASSIF", _("Passif")
    CHARGE = "CHARGE", _("Charge")
    PRODUIT = "PRODUIT", _("Produit")
    MIXTE = "MIXTE", _("Mixte")
    NEUTRE = "NEUTRE", _("Neutre")


class SensCompte(models.TextChoices):
    DEBIT = "DEBIT", _("Débit")
    CREDIT = "CREDIT", _("Crédit")
    MIXTE = "MIXTE", _("Mixte")


class TypeCompteComptable(models.TextChoices):
    CLASSE = "classe", _("Classe")
    GROUPE = "groupe", _("Groupe")
    COMPTE = "compte", _("Compte")
    SOUS_COMPTE = "sous_compte", _("Sous-compte")


class CategorieCompte(models.TextChoices):
    BILAN = "bilan", _("Bilan")
    RESULTAT = "resultat", _("Résultat")
    HORS_BILAN = "hors_bilan", _("Hors bilan")
    # Classe 9 du SYSCOHADA : comptes reflechis, de couts, d'ecarts, de
    # liaisons internes. Ils font partie du referentiel officiel ; sans
    # cette categorie, un plan comptable complet ne pouvait pas etre
    # charge sans violer les choix du modele.
    ANALYTIQUE = "analytique", _("Analytique")


class CompteComptable(models.Model):
    """Plan comptable SYSCOHADA — hiérarchique."""

    code = models.CharField(_("Code"), max_length=20)
    libelle = models.CharField(_("Libellé"), max_length=200)
    nature = models.CharField(_("Nature"), max_length=10, choices=NatureCompte.choices)
    sens = models.CharField(_("Sens"), max_length=10, choices=SensCompte.choices)
    parent = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True,
        related_name="enfants", verbose_name=_("Compte parent"),
    )
    niveau = models.IntegerField(_("Niveau"), default=1)
    type_compte = models.CharField(
        _("Type"), max_length=20, choices=TypeCompteComptable.choices,
        default=TypeCompteComptable.COMPTE,
    )
    est_mouvement = models.BooleanField(_("Movable"), default=True)
    categorie = models.CharField(
        _("Catégorie"), max_length=20, choices=CategorieCompte.choices,
        default=CategorieCompte.BILAN,
    )
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
        verbose_name = _("Compte comptable")
        verbose_name_plural = _("Comptes comptables")
        ordering = ["code"]
        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["parent"]),
        ]

    def __str__(self):
        return f"{self.code} - {self.libelle}"

    def clean(self):
        if self.parent_id:
            if self.parent_id == self.pk:
                raise ValidationError("Un compte ne peut pas être son propre parent.")
            if (self.parent.entreprise_id or "") != (self.entreprise_id or ""):
                raise ValidationError(
                    "Le compte parent doit appartenir à la même entreprise."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def classe(self):
        return self.code[0] if self.code else ""

    @property
    def est_lettrable(self):
        lettrables = ["40", "41", "42", "43", "44", "45"]
        return any(self.code.startswith(c) for c in lettrables)

    @property
    def est_tva(self):
        tva = ["443", "444", "445"]
        return any(self.code.startswith(c) for c in tva)

    @property
    def solde_normal(self):
        # Le plan peut imposer un sens précis pour les comptes de sens
        # contraire (amortissements, dépréciations, résultat déficitaire...).
        if self.sens and self.sens != SensCompte.MIXTE:
            return self.sens
        if self.nature in (NatureCompte.ACTIF, NatureCompte.CHARGE):
            return SensCompte.DEBIT
        if self.nature in (NatureCompte.PASSIF, NatureCompte.PRODUIT):
            return SensCompte.CREDIT
        return SensCompte.MIXTE
