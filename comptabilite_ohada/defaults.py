from appconf import AppConf


class ComptabiliteOhadaAppConf(AppConf):
    """Safe defaults: no automatic posting of operational cash movements."""

    DEFAULT_CURRENCY = "XOF"
    EXERCICE_TYPE = "ANNUEL"
    AUTO_CREATE_JOURNALS = False
    AUTO_CREATE_ENTRY = False
    TIERS_MODEL = None
    COMPTES_INTEGRATION_ENABLED = False
    STOCK_INTEGRATION_ENABLED = False

    class Meta:
        prefix = "COMPTABILITE_OHADA"
