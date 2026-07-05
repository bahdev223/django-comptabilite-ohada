from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ComptabiliteOhadaConfig(AppConfig):
    name = "comptabilite_ohada"
    verbose_name = _("Comptabilité SYSCOHADA")
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from .integrations import connect_integrations  # noqa: F401
        connect_integrations()
