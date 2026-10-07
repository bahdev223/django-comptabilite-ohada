from django.db import models
from django.utils.translation import gettext_lazy as _


class EvenementMetier(models.Model):
    """Inbox idempotente des événements métiers envoyés par des systèmes externes."""

    STATUTS = [
        ("RECU", _("Reçu")),
        ("TRAITE", _("Traité")),
        ("IGNORE", _("Ignoré")),
        ("ERREUR", _("Erreur")),
    ]

    entreprise_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    type_evenement = models.CharField(max_length=100, db_index=True)
    source_system = models.CharField(max_length=100, db_index=True)
    source_type = models.CharField(max_length=100, blank=True, default="")
    source_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    idempotency_key = models.CharField(max_length=255)
    payload = models.JSONField(default=dict)
    statut = models.CharField(max_length=20, choices=STATUTS, default="RECU", db_index=True)
    ecriture = models.ForeignKey(
        "EcritureComptable", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="evenements_sources"
    )
    erreur = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["entreprise_id", "idempotency_key"],
                name="uniq_evenement_idempotent_par_entreprise",
            )
        ]
        ordering = ["-created_at"]
        verbose_name = _("Événement métier")
        verbose_name_plural = _("Événements métier")

    def __str__(self):
        return f"{self.type_evenement} - {self.idempotency_key}"


class RegleEvenementComptable(models.Model):
    """Associe un type d'événement externe à une règle comptable sans couplage métier."""

    entreprise_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    type_evenement = models.CharField(max_length=100)
    code_regle = models.CharField(max_length=100)
    actif = models.BooleanField(default=True)
    configuration = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = [["entreprise_id", "type_evenement"]]
        ordering = ["type_evenement"]
        verbose_name = _("Règle d'événement comptable")
        verbose_name_plural = _("Règles d'événements comptables")

    def __str__(self):
        return f"{self.type_evenement} -> {self.code_regle}"
