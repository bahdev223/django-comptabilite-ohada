from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from ..models import ReleveBancaire, LigneReleveBancaire
from ..models import EcritureComptable, LigneEcritureComptable
from ..signals.ecriture import rapprochement_valide
from ..models import CompteComptable
from ..tenancy import require_tenant, check_owned
from django.core.exceptions import ValidationError


class RapprochementService:
    """Service de rapprochement bancaire."""

    @staticmethod
    @transaction.atomic
    def creer_releve(compte_comptable_code, date_debut, date_fin,
                     solde_ouverture, solde_cloture):
        tenant = require_tenant()
        if not CompteComptable.objects.filter(
            entreprise_id=tenant, code=compte_comptable_code, actif=True
        ).exists():
            raise ValidationError("Compte bancaire absent du plan de l'entreprise.")
        return ReleveBancaire.objects.create(
            entreprise_id=tenant, compte_comptable_code=compte_comptable_code,
            date_debut=date_debut,
            date_fin=date_fin,
            solde_ouverture=solde_ouverture,
            solde_cloture=solde_cloture,
        )

    @staticmethod
    def ajouter_ligne(releve, date_operation, libelle, montant, sens, reference=""):
        check_owned(releve, what="Relevé bancaire")
        if releve.statut != "BROUILLON":
            raise ValidationError("Relevé déjà rapproché.")
        return LigneReleveBancaire.objects.create(
            releve=releve,
            date_operation=date_operation,
            libelle=libelle,
            montant=montant,
            sens=sens,
            reference=reference,
        )

    @staticmethod
    def pointer(releve, ligne_id):
        check_owned(releve, what="Relevé bancaire")
        if releve.statut != "BROUILLON":
            raise ValidationError("Relevé déjà rapproché.")
        ligne = releve.lignes.filter(id=ligne_id).first()
        if ligne:
            ligne.pointe = True
            ligne.save(update_fields=["pointe"])
        return releve

    @staticmethod
    def depointer(releve, ligne_id):
        check_owned(releve, what="Relevé bancaire")
        if releve.statut != "BROUILLON":
            raise ValidationError("Relevé déjà rapproché.")
        ligne = releve.lignes.filter(id=ligne_id).first()
        if ligne:
            ligne.pointe = False
            ligne.save(update_fields=["pointe"])
        return releve

    @staticmethod
    @transaction.atomic
    def valider(releve, user=None):
        check_owned(releve, what="Relevé bancaire")
        if releve.statut != "BROUILLON":
            raise ValidationError("Relevé déjà rapproché.")
        non_pointees = releve.lignes.filter(pointe=False)
        if non_pointees.exists():
            raise ValueError(f"{non_pointees.count()} ligne(s) non pointée(s)")

        solde_calcule = releve.solde_ouverture
        for ligne in releve.lignes.order_by("date_operation"):
            if ligne.sens == "CREDIT":
                solde_calcule += ligne.montant
            else:
                solde_calcule -= ligne.montant

        if solde_calcule != releve.solde_cloture:
            raise ValueError(
                f"Solde calculé ({solde_calcule:,.0f}) ≠ solde relevé ({releve.solde_cloture:,.0f})"
            )

        releve.statut = "RAPPROCHE"
        releve.save(update_fields=["statut"])

        rapprochement_valide.send(
            sender=RapprochementService,
            instance=releve,
            user=user,
        )

        return releve
