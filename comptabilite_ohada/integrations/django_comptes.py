"""
Intégration avec django-comptes.

Écoute les signaux de django-comptes pour créer automatiquement
les écritures comptables correspondant aux mouvements financiers.
"""

from django.dispatch import receiver


def connect():
    """Connecte les handlers aux signaux de django-comptes."""
    try:
        from comptes.signals.mouvement import (
            mouvement_valide, mouvement_annule, transfert_effectue,
        )
    except ImportError:
        return

    from comptabilite_ohada.services.ecriture_service import EcritureService

    @receiver(mouvement_valide)
    def on_mouvement_valide(sender, instance, nature, montant, user, **kwargs):
        """À chaque mouvement validé dans comptes, créer l'écriture comptable."""
        compte = instance.compte
        compte_code = compte.compte_comptable_code or "571"

        if nature in ("ENCAISSEMENT", "TRANSFERT"):
            EcritureService.creer_ecriture_vente(
                compte_caisse_code=compte_code,
                montant=montant,
                libelle=instance.libelle,
                compte_produit_code="706",
                user=user,
            )
        elif nature == "DECAISSEMENT":
            EcritureService.creer_ecriture_charge(
                compte_caisse_code=compte_code,
                montant=montant,
                libelle=instance.libelle,
                compte_charge_code="658",
                user=user,
            )

    @receiver(transfert_effectue)
    def on_transfert_effectue(sender, instance, source, destination, montant, user, **kwargs):
        """À chaque transfert comptes → comptes, créer l'écriture de virement."""
        source_code = source.compte_comptable_code or "571"
        dest_code = destination.compte_comptable_code or "571"

        EcritureService.creer_ecriture_transfert(
            compte_source_code=source_code,
            compte_dest_code=dest_code,
            montant=montant,
            libelle=instance.notes or f"Virement {source.nom} → {destination.nom}",
            user=user,
        )

    from comptes.signals.mouvement import mouvement_annule

    @receiver(mouvement_annule)
    def on_mouvement_annule(sender, instance, annulation, user, **kwargs):
        """À chaque annulation, créer l'écriture d'annulation."""
        compte = instance.compte
        compte_code = compte.compte_comptable_code or "571"
        EcritureService.creer_ecriture_regularisation(
            montant=instance.montant,
            libelle=f"Annulation {instance.reference or instance.libelle}",
            compte_debit_code=compte_code,
            compte_credit_code=compte_code,
            user=user,
        )
