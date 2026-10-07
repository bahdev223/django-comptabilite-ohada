import hashlib
import hmac
import secrets

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class OrganisationComptable(models.Model):
    """Registre local optionnel des entreprises pour le mode standalone."""

    code = models.CharField(max_length=100, unique=True)
    nom = models.CharField(max_length=200)
    actif = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nom"]
        verbose_name = _("Organisation comptable")
        verbose_name_plural = _("Organisations comptables")

    def __str__(self):
        return f"{self.code} - {self.nom}"


class AccesEntrepriseComptable(models.Model):
    """Droit d'un utilisateur local sur une entreprise comptable."""

    ROLES = [
        ("ADMIN", _("Administrateur")),
        ("COMPTABLE", _("Comptable")),
        ("VALIDATEUR", _("Validateur")),
        ("LECTURE", _("Lecture seule")),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="acces_comptables",
    )
    entreprise = models.ForeignKey(
        OrganisationComptable,
        on_delete=models.CASCADE,
        related_name="acces_utilisateurs",
    )
    role = models.CharField(max_length=20, choices=ROLES, default="LECTURE")
    actif = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = [["user", "entreprise"]]
        verbose_name = _("Accès entreprise comptable")
        verbose_name_plural = _("Accès entreprises comptables")

    def __str__(self):
        return f"{self.user} -> {self.entreprise.code} ({self.role})"



class ApplicationClienteComptable(models.Model):
    """Client machine-to-machine autorisé à appeler l'API comptable."""

    entreprise = models.ForeignKey(
        OrganisationComptable,
        on_delete=models.CASCADE,
        related_name="applications_clientes",
    )
    nom = models.CharField(max_length=150)
    prefixe = models.CharField(max_length=16, unique=True, db_index=True)
    secret_hash = models.CharField(max_length=64)
    scopes = models.JSONField(default=list, blank=True)
    actif = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [["entreprise", "nom"]]
        ordering = ["entreprise__code", "nom"]
        verbose_name = _("Application cliente comptable")
        verbose_name_plural = _("Applications clientes comptables")

    def __str__(self):
        return f"{self.entreprise.code} - {self.nom}"

    @staticmethod
    def _hash(secret):
        return hashlib.sha256(secret.encode("utf-8")).hexdigest()

    def verifier_secret(self, secret):
        return hmac.compare_digest(
            self.secret_hash,
            self._hash(secret),
        )

    @classmethod
    def generer_cle(cls, entreprise, nom, scopes=None):
        # Le secret brut n'est retourné qu'à la création et n'est jamais stocké.
        secret = "acct_" + secrets.token_urlsafe(32)
        prefixe = secret[:16]
        objet = cls.objects.create(
            entreprise=entreprise,
            nom=nom,
            prefixe=prefixe,
            secret_hash=cls._hash(secret),
            scopes=list(scopes or []),
        )
        return objet, secret
