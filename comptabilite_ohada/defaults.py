from django.conf import settings
from appconf import AppConf


class ComptabiliteOhadaAppConf(AppConf):
    """
    Configuration globale du module comptabilite OHADA.

    Chaque projet peut surcharger dans settings.COMPTABILITE_OHADA:

        COMPTABILITE_OHADA = {
            'DEFAULT_CURRENCY': 'FCFA',
            'EXERCICE_TYPE': 'ANNUEL',       # ANNUEL ou CONTINU
            'AUTO_CREATE_JOURNALS': True,
            'AUTO_CREATE_ENTRY': True,
            'TIERS_MODEL': None,              # ex: 'clients.Client'
            'COMPTES_INTEGRATION_ENABLED': True,
            'STOCK_INTEGRATION_ENABLED': True,
        }
    """

    DEFAULT_CURRENCY = "FCFA"
    EXERCICE_TYPE = "ANNUEL"
    AUTO_CREATE_JOURNALS = True
    AUTO_CREATE_ENTRY = True
    TIERS_MODEL = None
    COMPTES_INTEGRATION_ENABLED = True
    STOCK_INTEGRATION_ENABLED = True

    class Meta:
        prefix = "COMPTABILITE_OHADA"
