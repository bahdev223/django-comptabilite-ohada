from decimal import Decimal
from datetime import date, datetime

from django.db import transaction
from django.utils import timezone

from ..models import EcritureComptable, LigneEcritureComptable, JournalComptable
from ..models import CompteComptable, ExerciceComptable
from ..signals.ecriture import ecriture_validee
from django.core.exceptions import ValidationError
from ..tenancy import require_enterprise, require_owned, validate_entry


class EcritureService:
    """Service central de création d'écritures comptables — point d'entrée unique."""

    # ─── Helpers ──────────────────────────────────────────────

    @classmethod
    def get_exercice(cls, date_operation=None, *, entreprise_id=None):
        entreprise_id = require_enterprise(entreprise_id)
        if date_operation is None:
            date_operation = date.today()
        exercice = ExerciceComptable.objects.filter(
            entreprise_id=entreprise_id,
            date_debut__lte=date_operation,
            date_fin__gte=date_operation,
            cloture=False,
        ).first()
        return exercice

    @classmethod
    def get_or_create_journal(cls, code, libelle, type_journal, *, entreprise_id=None):
        entreprise_id = require_enterprise(entreprise_id)
        journal, _ = JournalComptable.objects.get_or_create(
            entreprise_id=entreprise_id, code=code,
            defaults={"libelle": libelle, "type_journal": type_journal, "actif": True},
        )
        return journal

    @classmethod
    def get_compte(cls, code_or_id, *, entreprise_id=None):
        entreprise_id = require_enterprise(entreprise_id)
        if code_or_id is None:
            return None
        if isinstance(code_or_id, int):
            return CompteComptable.objects.filter(entreprise_id=entreprise_id, id=code_or_id, actif=True).first()
        compte = CompteComptable.objects.filter(entreprise_id=entreprise_id, code=str(code_or_id), actif=True).first()
        if compte:
            return compte
        if isinstance(code_or_id, str) and code_or_id.isdigit():
            return CompteComptable.objects.filter(entreprise_id=entreprise_id, id=int(code_or_id), actif=True).first()
        return None

    @classmethod
    def get_compte_par_type_caisse(cls, type_caisse, *, entreprise_id=None):
        mapping = {"ESPECES": "571", "BANQUE": "521", "MOBILE_MONEY": "581"}
        code = mapping.get(type_caisse, "571")
        return cls.get_compte(code, entreprise_id=entreprise_id)

    @classmethod
    def generer_reference(cls, prefix, dt=None, seq=None):
        if dt is None:
            dt = datetime.now()
        if seq:
            return f"{prefix}-{dt.strftime('%Y%m%d')}-{seq}"
        return f"{prefix}-{dt.strftime('%Y%m%d%H%M%S%f')}"

    @classmethod
    @transaction.atomic
    def creer_ecriture(cls, reference, date_ecriture, libelle, journal, lignes,
                       exercice=None, piece=None, validee=True, user=None, *, entreprise_id=None):
        entreprise_id = require_enterprise(entreprise_id)
        lignes = list(lignes)
        date_ecriture = EcritureComptable._meta.get_field('date_ecriture').to_python(date_ecriture)
        if exercice is None:
            exercice = cls.get_exercice(date_ecriture, entreprise_id=entreprise_id)
        if exercice is None:
            raise ValidationError('Aucun exercice ouvert ne couvre cette date.')
        # Serialize creation with closure/validation on the fiscal-year row.
        exercice = ExerciceComptable.objects.select_for_update().filter(
            pk=exercice.pk, entreprise_id=entreprise_id).first()
        journal, exercice, lignes = validate_entry(
            date_ecriture, journal, exercice, lignes, entreprise_id)

        ecriture = EcritureComptable.objects.create(
            entreprise_id=entreprise_id,
            reference=reference,
            date_ecriture=date_ecriture,
            libelle=libelle,
            journal=journal,
            piece=piece,
            exercice=exercice,
            validee=False,
            created_by=user.username if hasattr(user, "username") and user else str(user or ""),
        )

        for ligne in lignes:
            LigneEcritureComptable.objects.create(
                ecriture=ecriture,
                compte=ligne["compte"],
                debit=ligne.get("debit", Decimal("0.00")),
                credit=ligne.get("credit", Decimal("0.00")),
                libelle=ligne.get("libelle", libelle),
            )

        if validee:
            from .exercice_service import ValidationService
            ecriture = ValidationService.valider_ecriture(ecriture, user=user, entreprise_id=entreprise_id)
            ecriture_validee.send(
                sender=EcritureService,
                instance=ecriture,
                lignes=lignes,
                user=user,
            )

        return ecriture

    # ─── Ventes ───────────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def creer_ecriture_vente(cls, compte_caisse_code, montant, libelle,
                             compte_produit_code, user=None, *, entreprise_id=None):
        journal = cls.get_or_create_journal("VN", "Ventes", "VENTES", entreprise_id=entreprise_id)
        compte_caisse = cls.get_compte(compte_caisse_code, entreprise_id=entreprise_id)
        compte_produit = cls.get_compte(compte_produit_code, entreprise_id=entreprise_id)
        ref = cls.generer_reference("VN")
        return cls.creer_ecriture(ref, date.today(), libelle, journal, [
            {"compte": compte_caisse, "debit": montant, "libelle": "Encaissement vente"},
            {"compte": compte_produit, "credit": montant, "libelle": libelle},
        ], user=user, entreprise_id=entreprise_id)

    @classmethod
    @transaction.atomic
    def creer_ecriture_facture_vente(cls, montant_ttc, montant_tva, libelle,
                                     compte_client_code, compte_produit_code,
                                     compte_tva_code=None, user=None, *, entreprise_id=None):
        journal = cls.get_or_create_journal("VN", "Ventes", "VENTES", entreprise_id=entreprise_id)
        cc = cls.get_compte(compte_client_code, entreprise_id=entreprise_id)
        cp = cls.get_compte(compte_produit_code, entreprise_id=entreprise_id)
        ref = cls.generer_reference("FV")
        lignes = [
            {"compte": cc, "debit": montant_ttc, "libelle": libelle},
            {"compte": cp, "credit": montant_ttc - montant_tva, "libelle": libelle},
        ]
        if montant_tva > 0 and compte_tva_code:
            lignes.append({
                "compte": cls.get_compte(compte_tva_code, entreprise_id=entreprise_id),
                "credit": montant_tva, "libelle": f"TVA {libelle}",
            })
        return cls.creer_ecriture(ref, date.today(), libelle, journal, lignes, user=user, entreprise_id=entreprise_id)

    # ─── Achats / Fournisseurs ────────────────────────────────

    @classmethod
    @transaction.atomic
    def creer_ecriture_achat(cls, montant_ttc, montant_tva, montant_ht, libelle,
                             compte_charge_code, compte_fournisseur_code,
                             compte_tva_code=None, user=None, *, entreprise_id=None):
        journal = cls.get_or_create_journal("AC", "Achats", "ACHATS", entreprise_id=entreprise_id)
        cch = cls.get_compte(compte_charge_code, entreprise_id=entreprise_id)
        cf = cls.get_compte(compte_fournisseur_code, entreprise_id=entreprise_id)
        ref = cls.generer_reference("AC")
        lignes = [
            {"compte": cch, "debit": montant_ht, "libelle": libelle},
            {"compte": cf, "credit": montant_ttc, "libelle": libelle},
        ]
        if montant_tva > 0 and compte_tva_code:
            lignes.append({
                "compte": cls.get_compte(compte_tva_code, entreprise_id=entreprise_id),
                "debit": montant_tva, "libelle": f"TVA {libelle}",
            })
        return cls.creer_ecriture(ref, date.today(), libelle, journal, lignes, user=user, entreprise_id=entreprise_id)

    @classmethod
    @transaction.atomic
    def creer_ecriture_charge(cls, compte_caisse_code, montant, libelle,
                              compte_charge_code, date_operation=None, user=None, *, entreprise_id=None):
        if date_operation is None:
            date_operation = date.today()
        journal = cls._journal_paiement(compte_caisse_code, entreprise_id=entreprise_id)
        compte_caisse = cls.get_compte(compte_caisse_code, entreprise_id=entreprise_id)
        cc = cls.get_compte(compte_charge_code, entreprise_id=entreprise_id) or cls.get_compte("658", entreprise_id=entreprise_id)
        now = datetime.now()
        ref = cls.generer_reference("CH", now)
        return cls.creer_ecriture(ref, date_operation, libelle, journal, [
            {"compte": cc, "debit": montant, "libelle": libelle},
            {"compte": compte_caisse, "credit": montant, "libelle": f"Paiement {libelle}"},
        ], piece=f"DEP-{date_operation.strftime('%Y%m%d')}", user=user, entreprise_id=entreprise_id)

    # ─── Trésorerie ───────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def creer_ecriture_encaissement(cls, compte_caisse_code, montant, libelle,
                                   compte_contrepartie_code, user=None, *, entreprise_id=None):
        """A receipt settles an explicit counterpart; sales use the sales contract."""
        caisse = cls.get_compte(compte_caisse_code, entreprise_id=entreprise_id)
        contrepartie = cls.get_compte(compte_contrepartie_code, entreprise_id=entreprise_id)
        if caisse is None or contrepartie is None or not caisse.code.startswith('5') or contrepartie.code.startswith(('5', '7')):
            raise ValidationError('Encaissement : trésorerie et contrepartie hors vente/transfert requises.')
        journal = cls._journal_paiement(compte_caisse_code, entreprise_id=entreprise_id)
        return cls.creer_ecriture(cls.generer_reference('ENC'), date.today(), libelle, journal, [
            {'compte': caisse, 'debit': montant},
            {'compte': contrepartie, 'credit': montant},
        ], user=user, entreprise_id=entreprise_id)

    @classmethod
    def _journal_paiement(cls, compte_caisse_code, *, entreprise_id=None):
        if compte_caisse_code and str(compte_caisse_code).startswith("52"):
            return cls.get_or_create_journal("BQ", "Banque", "BANQUE", entreprise_id=entreprise_id)
        return cls.get_or_create_journal("CS", "Caisse", "CAISSE", entreprise_id=entreprise_id)

    @classmethod
    @transaction.atomic
    def creer_ecriture_transfert(cls, compte_source_code, compte_dest_code,
                                 montant, libelle, user=None, *, entreprise_id=None):
        source = cls.get_compte(compte_source_code, entreprise_id=entreprise_id)
        destination = cls.get_compte(compte_dest_code, entreprise_id=entreprise_id)
        if source is None or destination is None or source.pk == destination.pk or not all(
            c.code.startswith('5') for c in (source, destination)
        ):
            raise ValidationError('Transfert entre deux comptes de trésorerie distincts obligatoire.')
        journal = cls.get_or_create_journal("TR", "Transferts", "CAISSE", entreprise_id=entreprise_id)
        ref = cls.generer_reference("TRF")
        return cls.creer_ecriture(ref, date.today(), libelle, journal, [
            {"compte": cls.get_compte(compte_dest_code, entreprise_id=entreprise_id), "debit": montant,
             "libelle": f"Transfert reçu"},
            {"compte": cls.get_compte(compte_source_code, entreprise_id=entreprise_id), "credit": montant,
             "libelle": f"Transfert émis"},
        ], user=user, entreprise_id=entreprise_id)

    @classmethod
    @transaction.atomic
    def creer_ecriture_depot_banque(cls, compte_caisse_code, montant, libelle, user=None, *, entreprise_id=None):
        journal = cls.get_or_create_journal("BQ", "Banque", "BANQUE", entreprise_id=entreprise_id)
        ref = cls.generer_reference("DB")
        return cls.creer_ecriture(ref, date.today(), libelle, journal, [
            {"compte": cls.get_compte("521", entreprise_id=entreprise_id), "debit": montant, "libelle": "Dépôt banque"},
            {"compte": cls.get_compte(compte_caisse_code, entreprise_id=entreprise_id), "credit": montant,
             "libelle": f"Dépôt depuis caisse"},
        ], user=user, entreprise_id=entreprise_id)

    @classmethod
    @transaction.atomic
    def creer_ecriture_retrait_banque(cls, compte_caisse_code, montant, libelle, user=None, *, entreprise_id=None):
        journal = cls.get_or_create_journal("BQ", "Banque", "BANQUE", entreprise_id=entreprise_id)
        ref = cls.generer_reference("RB")
        return cls.creer_ecriture(ref, date.today(), libelle, journal, [
            {"compte": cls.get_compte(compte_caisse_code, entreprise_id=entreprise_id), "debit": montant,
             "libelle": f"Retrait banque vers caisse"},
            {"compte": cls.get_compte("521", entreprise_id=entreprise_id), "credit": montant, "libelle": "Retrait banque"},
        ], user=user, entreprise_id=entreprise_id)

    # ─── Paie ─────────────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def creer_ecriture_salaire(cls, montant_brut, montant_net, montant_cnps,
                               montant_impot, montant_avances, libelle,
                               compte_caisse_code=None, user=None, *, entreprise_id=None):
        journal = cls.get_or_create_journal("PA", "Paie", "CAISSE", entreprise_id=entreprise_id)
        caisse = cls.get_compte(compte_caisse_code, entreprise_id=entreprise_id) if compte_caisse_code else cls.get_compte("571", entreprise_id=entreprise_id)
        ref = cls.generer_reference("PAIE")
        lignes = [
            {"compte": cls.get_compte("661", entreprise_id=entreprise_id), "debit": montant_brut, "libelle": libelle},
            {"compte": caisse, "credit": montant_net, "libelle": "Net à payer"},
        ]
        if montant_cnps > 0:
            lignes.append({"compte": cls.get_compte("431", entreprise_id=entreprise_id), "credit": montant_cnps, "libelle": "CNPS"})
        if montant_impot > 0:
            lignes.append({"compte": cls.get_compte("447", entreprise_id=entreprise_id), "credit": montant_impot, "libelle": "IRPP"})
        if montant_avances > 0:
            lignes.append({"compte": cls.get_compte("425", entreprise_id=entreprise_id), "debit": montant_avances, "libelle": "Avances déduites"})
        return cls.creer_ecriture(ref, date.today(), libelle, journal, lignes, user=user, entreprise_id=entreprise_id)

    # ─── Stock ────────────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def creer_ecriture_entree_stock(cls, montant, libelle, compte_stock="31",
                                    compte_variation="6031", user=None, *, entreprise_id=None):
        journal = cls.get_or_create_journal("ST", "Stock", "ACHATS", entreprise_id=entreprise_id)
        ref = cls.generer_reference("ES")
        return cls.creer_ecriture(ref, date.today(), libelle, journal, [
            {"compte": cls.get_compte(compte_stock, entreprise_id=entreprise_id), "debit": montant, "libelle": libelle},
            {"compte": cls.get_compte(compte_variation, entreprise_id=entreprise_id), "credit": montant, "libelle": libelle},
        ], user=user, entreprise_id=entreprise_id)

    @classmethod
    @transaction.atomic
    def creer_ecriture_sortie_stock(cls, montant, libelle, compte_charge="6032",
                                    compte_stock="31", user=None, *, entreprise_id=None):
        journal = cls.get_or_create_journal("ST", "Stock", "ACHATS", entreprise_id=entreprise_id)
        ref = cls.generer_reference("SS")
        return cls.creer_ecriture(ref, date.today(), libelle, journal, [
            {"compte": cls.get_compte(compte_charge, entreprise_id=entreprise_id), "debit": montant, "libelle": libelle},
            {"compte": cls.get_compte(compte_stock, entreprise_id=entreprise_id), "credit": montant, "libelle": libelle},
        ], user=user, entreprise_id=entreprise_id)

    @classmethod
    @transaction.atomic
    def creer_ecriture_inventaire(cls, ecart, libelle, compte_stock="31",
                                  compte_charge="658", compte_produit="758", user=None, *, entreprise_id=None):
        journal = cls.get_or_create_journal("ST", "Stock", "ACHATS", entreprise_id=entreprise_id)
        ref = cls.generer_reference("INV")
        if ecart >= 0:
            lignes = [
                {"compte": cls.get_compte(compte_stock, entreprise_id=entreprise_id), "debit": ecart, "libelle": libelle},
                {"compte": cls.get_compte(compte_produit, entreprise_id=entreprise_id), "credit": ecart, "libelle": libelle},
            ]
        else:
            e = -ecart
            lignes = [
                {"compte": cls.get_compte(compte_charge, entreprise_id=entreprise_id), "debit": e, "libelle": libelle},
                {"compte": cls.get_compte(compte_stock, entreprise_id=entreprise_id), "credit": e, "libelle": libelle},
            ]
        return cls.creer_ecriture(ref, date.today(), libelle, journal, lignes, user=user, entreprise_id=entreprise_id)

    # ─── Immobilisations ──────────────────────────────────────

    @classmethod
    @transaction.atomic
    def creer_ecriture_acquisition_immo(cls, montant, libelle, compte_immo_code,
                                        compte_tiers_code=None, compte_caisse_code=None, user=None, *, entreprise_id=None):
        journal = cls.get_or_create_journal("INV", "Investissements", "ACHATS", entreprise_id=entreprise_id)
        ref = cls.generer_reference("ACQ")
        lignes = [
            {"compte": cls.get_compte(compte_immo_code, entreprise_id=entreprise_id), "debit": montant, "libelle": libelle},
        ]
        if compte_caisse_code:
            lignes.append({"compte": cls.get_compte(compte_caisse_code, entreprise_id=entreprise_id), "credit": montant, "libelle": libelle})
        elif compte_tiers_code:
            lignes.append({"compte": cls.get_compte(compte_tiers_code, entreprise_id=entreprise_id), "credit": montant, "libelle": libelle})
        else:
            lignes.append({"compte": cls.get_compte("404", entreprise_id=entreprise_id), "credit": montant, "libelle": libelle})
        return cls.creer_ecriture(ref, date.today(), libelle, journal, lignes, user=user, entreprise_id=entreprise_id)

    @classmethod
    @transaction.atomic
    def creer_ecriture_amortissement(cls, plan, user=None, *, entreprise_id=None):
        immobilisation = require_owned(plan.immobilisation, entreprise_id)
        journal = cls.get_or_create_journal("OD", "Opérations Diverses", "OD", entreprise_id=entreprise_id)
        ref = f"AMORT-{immobilisation.code}-{plan.periode.strftime('%Y%m')}"
        libelle = f"Amortissement {immobilisation.libelle} - {plan.periode.strftime('%m/%Y')}"
        ecriture = cls.creer_ecriture(ref, plan.periode, libelle, journal, [
            {"compte": immobilisation.compte_charge, "debit": plan.montant,
             "libelle": f"Dotation {immobilisation.libelle}"},
            {"compte": immobilisation.compte_amortissement, "credit": plan.montant,
             "libelle": f"Amortissement {immobilisation.libelle}"},
        ], exercice=cls.get_exercice(plan.periode, entreprise_id=entreprise_id), user=user, entreprise_id=entreprise_id)
        plan.ecriture_generee = True
        plan.ecriture_reference = ref
        plan.save(update_fields=["ecriture_generee", "ecriture_reference"])
        return ecriture

    # ─── Divers ───────────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def creer_ecriture_regularisation(cls, montant, libelle, compte_debit_code,
                                      compte_credit_code, user=None, *, entreprise_id=None):
        journal = cls.get_or_create_journal("OD", "Opérations Diverses", "OD", entreprise_id=entreprise_id)
        ref = cls.generer_reference("RG")
        return cls.creer_ecriture(ref, date.today(), libelle, journal, [
            {"compte": cls.get_compte(compte_debit_code, entreprise_id=entreprise_id), "debit": montant, "libelle": libelle},
            {"compte": cls.get_compte(compte_credit_code, entreprise_id=entreprise_id), "credit": montant, "libelle": libelle},
        ], user=user, entreprise_id=entreprise_id)

    @classmethod
    @transaction.atomic
    def creer_ecriture_cloture_exercice(cls, exercice, resultat, user=None, *, entreprise_id=None):
        journal = cls.get_or_create_journal("CL", "Clôture", "OD", entreprise_id=entreprise_id)
        ref = f"RES-{exercice.code}"
        libelle = f"Affectation résultat exercice {exercice.code}"
        if resultat >= 0:
            lignes = [
                {"compte": cls.get_compte("129", entreprise_id=entreprise_id), "debit": resultat,
                 "libelle": f"Bénéfice {exercice.code}"},
                {"compte": cls.get_compte("101", entreprise_id=entreprise_id), "credit": resultat,
                 "libelle": f"Capital - report bénéfice {exercice.code}"},
            ]
        else:
            r = abs(resultat)
            lignes = [
                {"compte": cls.get_compte("101", entreprise_id=entreprise_id), "debit": r,
                 "libelle": f"Imputation perte {exercice.code}"},
                {"compte": cls.get_compte("129", entreprise_id=entreprise_id), "credit": r,
                 "libelle": f"Perte {exercice.code}"},
            ]
        return cls.creer_ecriture(ref, exercice.date_fin, libelle, journal, lignes,
                                  exercice=exercice, user=user, entreprise_id=entreprise_id)

