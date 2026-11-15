"""An exercise owns one legal-policy decision, independent of subscriptions."""
from django.core.exceptions import ValidationError
from django.db import models


class PolicyQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError('Décision comptable : service transactionnel obligatoire.')

    def delete(self):
        raise ValidationError('Une décision comptable ne peut pas être supprimée.')

    def bulk_create(self, *args, **kwargs):
        raise ValidationError('Import direct de décisions comptables interdit.')

    def bulk_update(self, *args, **kwargs):
        raise ValidationError('Mutation directe de décisions comptables interdite.')


class AccountingPolicyAssignment(models.Model):
    exercise = models.OneToOneField('ExerciceComptable', on_delete=models.PROTECT,
                                   related_name='accounting_policy')
    system = models.CharField(max_length=6, choices=[('NORMAL', 'Système Normal'), ('SMT', 'SMT')])
    ruleset_version = models.CharField(max_length=60, blank=True)
    status = models.CharField(max_length=12, choices=[('draft', 'À confirmer'), ('confirmed', 'Confirmé')])
    decision = models.JSONField(default=dict)
    revision = models.PositiveIntegerField(default=1)
    decided_at = models.DateTimeField(null=True, blank=True)
    frozen_at = models.DateTimeField(null=True, blank=True)
    objects = PolicyQuerySet.as_manager()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(system__in=['NORMAL', 'SMT']), name='ohada_policy_system'),
            models.CheckConstraint(condition=models.Q(status__in=['draft', 'confirmed']), name='ohada_policy_status'),
            models.CheckConstraint(condition=models.Q(frozen_at__isnull=True) | models.Q(status='confirmed'), name='ohada_policy_frozen_confirmed'),
            models.CheckConstraint(condition=(models.Q(status='draft', decided_at__isnull=True)
                | models.Q(status='confirmed', decided_at__isnull=False)), name='ohada_policy_decided_state'),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('Décision existante : service transactionnel obligatoire.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Une décision comptable ne peut pas être supprimée.')
