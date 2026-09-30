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

    from comptabilite_ohada.models import EcritureComptable
    from comptabilite_ohada.services.ecriture_service import EcritureService
    from comptabilite_ohada.services.exercice_service import ValidationService

    @receiver(mouvement_valide)
    def on_mouvement_valide(sender, instance, nature, montant, user, **kwargs):
        """À chaque mouvement validé dans comptes, créer l'écriture comptable."""
        compte = instance.compte
        compte_code = compte.compte_comptable_code or "571"
        entreprise_id = str(getattr(compte, "entreprise_id", "") or "")
        source_ref = str(getattr(instance, "reference", "") or getattr(instance, "pk", ""))
        piece = f"DJANGO-COMPTES:{source_ref}"

        # Les transferts ont leur signal dédié ci-dessous. Les traiter ici
        # créerait une seconde écriture et les classerait à tort en vente.
        if nature == "ENCAISSEMENT":
            EcritureService.creer_ecriture_vente(
                compte_caisse_code=compte_code,
                montant=montant,
                libelle=instance.libelle,
                compte_produit_code="706",
                user=user,
                entreprise_id=entreprise_id,
                piece=piece,
                source_system="django-comptes",
                source_type="mouvement",
                source_id=source_ref,
                idempotency_key=f"django-comptes:mouvement:{source_ref}",
            )
        elif nature == "DECAISSEMENT":
            EcritureService.creer_ecriture_charge(
                compte_caisse_code=compte_code,
                montant=montant,
                libelle=instance.libelle,
                compte_charge_code="658",
                user=user,
                entreprise_id=entreprise_id,
                piece=piece,
                source_system="django-comptes",
                source_type="mouvement",
                source_id=source_ref,
                idempotency_key=f"django-comptes:mouvement:{source_ref}",
            )

    @receiver(transfert_effectue)
    def on_transfert_effectue(sender, instance, source, destination, montant, user, **kwargs):
        """À chaque transfert comptes → comptes, créer l'écriture de virement."""
        source_code = source.compte_comptable_code or "571"
        dest_code = destination.compte_comptable_code or "571"
        entreprise_id = str(getattr(source, "entreprise_id", "") or "")
        source_ref = str(getattr(instance, "reference", "") or getattr(instance, "pk", ""))

        EcritureService.creer_ecriture_transfert(
            compte_source_code=source_code,
            compte_dest_code=dest_code,
            montant=montant,
            libelle=instance.notes or f"Virement {source.nom} → {destination.nom}",
            user=user,
            entreprise_id=entreprise_id,
            piece=f"DJANGO-COMPTES:{source_ref}",
            source_system="django-comptes",
            source_type="transfert",
            source_id=source_ref,
            idempotency_key=f"django-comptes:transfert:{source_ref}",
        )

    from comptes.signals.mouvement import mouvement_annule

    @receiver(mouvement_annule)
    def on_mouvement_annule(sender, instance, annulation, user, **kwargs):
        """Contre-passe l'écriture réellement créée pour le mouvement source."""
        compte = instance.compte
        entreprise_id = str(getattr(compte, "entreprise_id", "") or "")
        source_ref = str(getattr(instance, "reference", "") or getattr(instance, "pk", ""))
        original = EcritureComptable.objects.filter(
            entreprise_id=entreprise_id,
            source_system="django-comptes",
            source_id=source_ref,
            validee=True,
        ).order_by("-created_at").first()
        if original is None:
            original = EcritureComptable.objects.filter(
                entreprise_id=entreprise_id,
                piece=f"DJANGO-COMPTES:{source_ref}",
                validee=True,
            ).order_by("-created_at").first()
        if original is None:
            return
        ValidationService.annuler_ecriture(
            original,
            user=user,
            raison=f"Annulation django-comptes {source_ref}",
        )
