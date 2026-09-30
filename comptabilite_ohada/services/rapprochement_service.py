from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ..models import ReleveBancaire, LigneReleveBancaire
from ..models import CompteComptable
from ..signals.ecriture import rapprochement_valide


class RapprochementService:
    """Service de rapprochement bancaire."""

    @staticmethod
    @transaction.atomic
    def creer_releve(compte_comptable_code, date_debut, date_fin,
                     solde_ouverture, solde_cloture, entreprise_id=""):
        entreprise_id = entreprise_id or ""
        compte = CompteComptable.objects.filter(
            entreprise_id=entreprise_id,
            code=compte_comptable_code,
            actif=True,
        ).first()
        if compte is None or not compte.code.startswith("5"):
            raise ValidationError(
                "Le compte de rapprochement doit être un compte de trésorerie actif de l'entreprise."
            )
        if date_fin < date_debut:
            raise ValidationError("La date de fin du relevé précède la date de début.")
        return ReleveBancaire.objects.create(
            entreprise_id=entreprise_id,
            compte_comptable_code=compte_comptable_code,
            date_debut=date_debut,
            date_fin=date_fin,
            solde_ouverture=solde_ouverture,
            solde_cloture=solde_cloture,
        )

    @staticmethod
    def ajouter_ligne(releve, date_operation, libelle, montant, sens, reference=""):
        if releve.statut == "RAPPROCHE":
            raise ValidationError("Un relevé rapproché est verrouillé.")
        if montant <= 0:
            raise ValidationError("Le montant d'une ligne de relevé doit être positif.")
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
        if releve.statut == "RAPPROCHE":
            raise ValidationError("Un relevé rapproché est verrouillé.")
        ligne = releve.lignes.filter(id=ligne_id).first()
        if ligne:
            ligne.pointe = True
            ligne.save(update_fields=["pointe"])
        return releve

    @staticmethod
    def depointer(releve, ligne_id):
        if releve.statut == "RAPPROCHE":
            raise ValidationError("Un relevé rapproché est verrouillé.")
        ligne = releve.lignes.filter(id=ligne_id).first()
        if ligne:
            ligne.pointe = False
            ligne.save(update_fields=["pointe"])
        return releve

    @staticmethod
    @transaction.atomic
    def valider(releve, user=None):
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
