import json
from decimal import Decimal
from importlib.resources import files as pkg_files

from django.db import transaction
from datetime import date

from ..models import CompteComptable, ConfigurationComptable, SoldeInitialComptable
from ..models import JournalComptable, ExerciceComptable
from .ecriture_service import EcritureService


class InitialisationService:
    """Initialisation du plan comptable SYSCOHADA et de la configuration."""

    @staticmethod
    def charger_plan_comptable(force=False, entreprise_id=""):
        entreprise_id = entreprise_id or ""
        # "force" synchronise les métadonnées du référentiel mais ne détruit
        # jamais des comptes pouvant porter un historique comptable.
        try:
            content = pkg_files("comptabilite_ohada.data").joinpath("plan_comptable.json").read_text(encoding="utf-8")
        except (ImportError, FileNotFoundError):
            return {"success": False, "error": "Fichier plan_comptable.json introuvable"}

        data = json.loads(content)
        comptes_data = data.get("comptes", [])
        if not comptes_data:
            return {"success": False, "error": "Aucun compte dans le fichier"}

        comptes_crees = 0
        parents = {}

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
            if force:
                compte, created = CompteComptable.objects.update_or_create(
                    entreprise_id=entreprise_id,
                    code=code,
                    defaults=defaults,
                )
            else:
                compte, created = CompteComptable.objects.get_or_create(
                    entreprise_id=entreprise_id,
                    code=code,
                    defaults=defaults,
                )
            if created:
                comptes_crees += 1
            parents[code] = compte

        for item in comptes_data:
            code = item["code"]
            parent_code = item.get("parent_code")
            if parent_code and parent_code in parents:
                compte = CompteComptable.objects.get(entreprise_id=entreprise_id, code=code)
                if compte.parent_id != parents[parent_code].pk:
                    compte.parent = parents[parent_code]
                    compte.save(update_fields=["parent"])

        config = ConfigurationComptable.get_config(entreprise_id)
        config.est_initialise = True
        config.date_initialisation = date.today()
        config.save(update_fields=["est_initialise", "date_initialisation", "updated_at"])

        return {"success": True, "comptes_crees": comptes_crees, "total": len(comptes_data)}

    @staticmethod
    @transaction.atomic
    def initialiser_journaux(entreprise_id=""):
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
                entreprise_id=entreprise_id or "",
                code=code,
                defaults={"libelle": libelle, "type_journal": type_j, "actif": True},
            )

    @staticmethod
    def initialiser_soldes(soldes, user=None, entreprise_id=""):
        entreprise_id = entreprise_id or ""
        config = ConfigurationComptable.get_config(entreprise_id)
        solde_init, _ = SoldeInitialComptable.objects.get_or_create(configuration=config)
        for field, value in soldes.items():
            if hasattr(solde_init, field):
                setattr(solde_init, field, Decimal(str(value)))
        solde_init.save()

        exercice = ExerciceComptable.objects.filter(
            cloture=False, entreprise_id=entreprise_id
        ).first()
        if not exercice:
            return solde_init

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
                    lignes.append({"compte": EcritureService.get_compte(compte_code, entreprise_id),
                                   "credit": montant})
                    total_credit += montant
                else:
                    lignes.append({"compte": EcritureService.get_compte(compte_code, entreprise_id),
                                   "debit": montant})
                    total_debit += montant

        if total_debit != total_credit:
            ecart = total_debit - total_credit
            if ecart > 0:
                lignes.append({"compte": EcritureService.get_compte(contrepartie, entreprise_id),
                               "credit": ecart})
            else:
                lignes.append({"compte": EcritureService.get_compte(contrepartie, entreprise_id),
                               "debit": -ecart})

        config = ConfigurationComptable.get_config(entreprise_id)
        EcritureService.creer_ecriture(
            reference=f"SI-{date.today().strftime('%Y%m%d')}",
            date_ecriture=date.today(),
            libelle="Situation initiale",
            journal=EcritureService.get_or_create_journal("OD", "OD", "OD", entreprise_id),
            lignes=lignes,
            exercice=exercice,
            user=user,
            entreprise_id=entreprise_id,
        )

        return solde_init
