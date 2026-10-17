from ..tenancy import require_enterprise, money
from django.core.exceptions import ValidationError
import json
from decimal import Decimal
from pathlib import Path
from importlib.resources import files as pkg_files

from django.db import transaction

from ..models import CompteComptable, ConfigurationComptable, SoldeInitialComptable
from ..models import JournalComptable, ExerciceComptable
from .ecriture_service import EcritureService


class InitialisationService:
    """Initialisation du plan comptable SYSCOHADA et de la configuration."""

    @staticmethod
    @transaction.atomic
    def charger_plan_comptable(force=False, *, entreprise_id=None):
        entreprise_id = require_enterprise(entreprise_id)

        try:
            content = pkg_files("comptabilite_ohada.data").joinpath("plan_comptable.json").read_text(encoding="utf-8")
        except (ImportError, FileNotFoundError):
            return {"success": False, "error": "Fichier plan_comptable.json introuvable"}

        data = json.loads(content)
        comptes_data = data.get("comptes", [])
        if not comptes_data:
            return {"success": False, "error": "Aucun compte dans le fichier"}

        # Serialize chart loading for this tenant, then fetch existing accounts
        # once. A distant PostgreSQL must not pay one round trip per chart row.
        config = ConfigurationComptable.get_config(entreprise_id=entreprise_id)
        config = ConfigurationComptable.objects.select_for_update().get(pk=config.pk)
        parents = {c.code: c for c in CompteComptable.objects.filter(entreprise_id=entreprise_id)}
        additions, changes = [], []
        fields = ['libelle', 'nature', 'sens', 'niveau', 'type_compte', 'est_mouvement', 'categorie', 'actif']
        for item in comptes_data:
            code = item["code"]
            parent_code = item.get("parent_code")
            defaults = {
                "libelle": item["libelle"],
                "nature": item.get("nature", "NEUTRE"),
                "sens": item.get("sens", "MIXTE"),
                "niveau": item.get("niveau", 1),
                "type_compte": item.get("type_compte", "compte"),
                "est_mouvement": item.get("est_mouvement", True),
                "categorie": item.get("categorie", "bilan"),
                "actif": item.get("actif", True),
            }
            if code not in parents:
                compte = CompteComptable(entreprise_id=entreprise_id, code=code, **defaults)
                additions.append(compte)
                parents[code] = compte
            elif force:
                compte = parents[code]
                for field, value in defaults.items():
                    setattr(compte, field, value)
                changes.append(compte)
        CompteComptable.objects.bulk_create(additions, batch_size=100)
        if changes:
            CompteComptable.objects.bulk_update(changes, fields, batch_size=100)

        parent_changes = []
        for item in comptes_data:
            code = item["code"]
            parent_code = item.get("parent_code")
            if parent_code and parent_code in parents:
                compte = parents[code]
                if compte.parent_id != parents[parent_code].pk:
                    compte.parent = parents[parent_code]
                    parent_changes.append(compte)
        if parent_changes:
            CompteComptable.objects.bulk_update(parent_changes, ['parent'], batch_size=100)

        config.est_initialise = True
        config.date_initialisation = date.today()
        config.save()

        return {"success": True, "comptes_crees": len(additions), "total": len(comptes_data)}

    @staticmethod
    @transaction.atomic
    def initialiser_journaux(*, entreprise_id=None):
        entreprise_id = require_enterprise(entreprise_id)
        defaults = [
            ("VN", "Ventes", "VENTES"),
            ("AC", "Achats", "ACHATS"),
            ("BQ", "Banque", "BANQUE"),
            ("CS", "Caisse", "CAISSE"),
            ("OD", "Opérations Diverses", "OD"),
            ("PA", "Paie", "PAIE"),
            ("ST", "Stock", "STOCK"),
            ("INV", "Immobilisations", "IMMO"),
            ("TR", "Transferts", "BANQUE"),
        ]
        for code, libelle, type_j in defaults:
            JournalComptable.objects.get_or_create(
                entreprise_id=entreprise_id, code=code,
                defaults={"libelle": libelle, "type_journal": type_j, "actif": True},
            )

    @staticmethod
    @transaction.atomic
    def initialiser_soldes(soldes, user=None, *, entreprise_id=None):
        entreprise_id = require_enterprise(entreprise_id)
        allowed = {'caisse', 'banque', 'stocks', 'clients', 'fournisseurs', 'capital_social'}
        if not isinstance(soldes, dict) or set(soldes) - allowed:
            raise ValidationError('Seuls les champs monétaires de situation initiale sont admis.')
        soldes = {field: money(value) for field, value in soldes.items()}
        config = ConfigurationComptable.get_config(entreprise_id=entreprise_id)
        solde_init, _ = SoldeInitialComptable.objects.get_or_create(configuration=config)
        for field, value in soldes.items():
            setattr(solde_init, field, value)
        solde_init.save()

        exercice = EcritureService.get_exercice(date.today(), entreprise_id=entreprise_id)
        if not exercice:
            raise ValidationError("Aucun exercice ouvert pour situation initiale.")

        contrepartie = config.contrepartie_situation
        mapping = {
            "caisse": "571",
            "banque": "521",
            "stocks": "31",
            "clients": "411",
            "fournisseurs": "401",
        }
        total_debit = Decimal("0.00")
        total_credit = Decimal("0.00")
        lignes = []

        for field, compte_code in mapping.items():
            montant = getattr(solde_init, field, Decimal("0.00"))
            if montant > 0:
                if field in ("fournisseurs",):
                    lignes.append({"compte": EcritureService.get_compte(compte_code, entreprise_id=entreprise_id),
                                   "credit": montant})
                    total_credit += montant
                else:
                    lignes.append({"compte": EcritureService.get_compte(compte_code, entreprise_id=entreprise_id),
                                   "debit": montant})
                    total_debit += montant

        if total_debit != total_credit:
            ecart = total_debit - total_credit
            if ecart > 0:
                lignes.append({"compte": EcritureService.get_compte(contrepartie, entreprise_id=entreprise_id),
                               "credit": ecart})
            else:
                lignes.append({"compte": EcritureService.get_compte(contrepartie, entreprise_id=entreprise_id),
                               "debit": -ecart})

        config = ConfigurationComptable.get_config(entreprise_id=entreprise_id)
        EcritureService.creer_ecriture(
            reference=f"SI-{date.today().strftime('%Y%m%d')}",
            date_ecriture=date.today(),
            libelle="Situation initiale",
            journal=EcritureService.get_or_create_journal("OD", "OD", "OD", entreprise_id=entreprise_id),
            lignes=lignes,
            exercice=exercice,
            user=user, entreprise_id=entreprise_id,
        )

        return solde_init


from datetime import date

