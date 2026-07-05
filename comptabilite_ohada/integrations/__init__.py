"""
Intégrations — ponts entre django-comptabilite-ohada et les autres packages.

Chaque fichier dans ce dossier écoute les signaux d'un autre package Django
et crée les écritures comptables correspondantes.

Principe :
    - django-comptes émet "mouvement_valide"
    - integrations/django_comptes.py écoute et crée l'écriture
    - Aucun couplage direct entre les packages
"""

from django.conf import settings


def connect_integrations():
    """Connecte toutes les intégrations activées."""
    from .django_comptes import connect as connect_comptes

    config = getattr(settings, "COMPTABILITE_OHADA", {})
    if config.get("COMPTES_INTEGRATION_ENABLED", True):
        try:
            connect_comptes()
        except ImportError:
            pass
