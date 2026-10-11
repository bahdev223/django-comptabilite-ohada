"""Tenant-scoped SYSCOHADA double-entry entry point.

All public service calls require a trusted tenant_scope() or an explicit tenant
identifier. No unscoped account, journal, fiscal period or ledger write is allowed.
"""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ..models import (
    CompteComptable, EcritureComptable, ExerciceComptable,
    JournalComptable, LigneEcritureComptable,
)
from ..tenancy import check_owned, require_tenant


def _operation_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValidationError("Date d'écriture ISO invalide.") from exc
    raise ValidationError("Date d'écriture obligatoire.")


def _montant(value):
    try:
        number = Decimal(str(value if value is not None else "0"))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError("Montant comptable invalide.") from exc
    if not number.is_finite() or number < 0 or number.as_tuple().exponent < -2:
        raise ValidationError("Montant négatif, non fini ou trop précis.")
    return number


class EcritureService:
    """Central ledger service: strict tenant, balances, dates and active accounts."""

    @classmethod
    def get_exercice(cls, date_operation=None, entreprise_id=None):
        tenant = require_tenant(entreprise_id)
        day = _operation_date(date_operation or date.today())
        exercises = list(
            ExerciceComptable.objects.filter(
                entreprise_id=tenant,
                date_debut__lte=day,
                date_fin__gte=day,
                cloture=False,
            ).order_by("pk")[:2]
        )
        if len(exercises) > 1:
            raise ValidationError("Plusieurs exercices ouverts couvrent cette date.")
        return exercises[0] if exercises else None

    @classmethod
    def get_or_create_journal(cls, code, libelle, type_journal, entreprise_id=None):
        tenant = require_tenant(entreprise_id)
        journal, _ = JournalComptable.objects.get_or_create(
            entreprise_id=tenant,
            code=code,
            defaults={"libelle": libelle, "type_journal": type_journal, "actif": True},
        )
        if not journal.actif:
            raise ValidationError("Journal comptable inactif.")
        return journal

    @classmethod
    def get_compte(cls, code_or_id, entreprise_id=None):
        tenant = require_tenant(entreprise_id)
        if code_or_id is None:
            return None
        base = CompteComptable.objects.filter(entreprise_id=tenant, actif=True)
        if isinstance(code_or_id, int):
            return base.filter(pk=code_or_id).first()
        # A numeric account code is never silently treated as a database PK.
        return base.filter(code=str(code_or_id)).first()

    @classmethod
    def get_compte_par_type_caisse(cls, type_caisse, entreprise_id=None):
        require_tenant(entreprise_id)
        mapping = {"ESPECES": "571", "BANQUE": "521", "MOBILE_MONEY": "581"}
        return cls.get_compte(mapping.get(type_caisse, "571"))

    @classmethod
    def generer_reference(cls, prefix, dt=None, seq=None):
        dt = dt or timezone.now()
        if seq is not None:
            return f"{prefix}-{dt.strftime('%Y%m%d')}-{seq}"
        return f"{prefix}-{dt.strftime('%Y%m%d%H%M%S%f')}"

    @classmethod
    @transaction.atomic
    def creer_ecriture(
        cls, reference, date_ecriture, libelle, journal, lignes,
        exercice=None, piece=None, validee=True, user=None, entreprise_id=None,
    ):
        tenant = require_tenant(entreprise_id)
        day = _operation_date(date_ecriture)
        if not isinstance(reference, str) or not reference.strip() or len(reference) > 50:
            raise ValidationError("Référence comptable obligatoire (50 caractères maximum).")
        check_owned(journal, tenant, what="Journal")
        if not journal.actif:
            raise ValidationError("Journal inactif.")

        if exercice is None:
            exercice = cls.get_exercice(day, entreprise_id=tenant)
        if exercice is None:
            raise ValidationError("Aucun exercice ouvert ne couvre la date d'écriture.")
        check_owned(exercice, tenant, what="Exercice")
        # Serialize ledger posting and fiscal closure on the same fiscal-year lock.
        exercice = ExerciceComptable.objects.select_for_update().get(
            pk=exercice.pk, entreprise_id=tenant
        )
        if exercice.cloture or not (exercice.date_debut <= day <= exercice.date_fin):
            raise ValidationError("Exercice clôturé ou date hors exercice.")

        prepared = []
        for index, data in enumerate(lignes, start=1):
            if not isinstance(data, dict):
                raise ValidationError(f"Ligne {index} invalide.")
            account = data.get("compte")
            if account is None:
                raise ValidationError(f"Ligne {index} : compte comptable introuvable.")
            check_owned(account, tenant, what=f"Compte de la ligne {index}")
            if not CompteComptable.objects.filter(
                pk=account.pk, entreprise_id=tenant, actif=True, est_mouvement=True
            ).exists():
                raise ValidationError(f"Ligne {index} : compte non mouvementable ou inactif.")
            debit, credit = _montant(data.get("debit")), _montant(data.get("credit"))
            if (debit > 0) == (credit > 0):
                raise ValidationError(f"Ligne {index} : un seul sens et montant positif requis.")
            prepared.append({
                "compte": account,
                "debit": debit,
                "credit": credit,
                "libelle": data.get("libelle") or libelle,
            })

        if len(prepared) < 2:
            raise ValidationError("Une écriture doit comporter au moins deux lignes.")
        total_debit = sum((line["debit"] for line in prepared), Decimal("0.00"))
        total_credit = sum((line["credit"] for line in prepared), Decimal("0.00"))
        if total_debit != total_credit or total_debit <= 0:
            raise ValidationError(
                f"Ecriture desequilibree : debit {total_debit}, credit {total_credit}."
            )

        entry = EcritureComptable.objects.create(
            entreprise_id=tenant,
            reference=reference.strip(),
            date_ecriture=day,
            libelle=libelle,
            journal=journal,
            exercice=exercice,
            piece=piece,
            validee=False,
            created_by=(
                user.get_username() if hasattr(user, "get_username") else str(user or "")
            ),
        )
        for line in prepared:
            LigneEcritureComptable.objects.create(ecriture=entry, **line)
        if validee:
            from .exercice_service import ValidationService
            ValidationService.valider_ecriture(entry, user=user, entreprise_id=tenant)
        return entry

    # ─── Ventes ───────────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def creer_ecriture_vente(cls, compte_caisse_code, montant, libelle,
                             compte_produit_code, user=None):
        journal = cls.get_or_create_journal("VN", "Ventes", "VENTES")
        compte_caisse = cls.get_compte(compte_caisse_code)
        compte_produit = cls.get_compte(compte_produit_code)
        ref = cls.generer_reference("VN")
        return cls.creer_ecriture(ref, date.today(), libelle, journal, [
            {"compte": compte_caisse, "debit": montant, "libelle": "Encaissement vente"},
            {"compte": compte_produit, "credit": montant, "libelle": libelle},
        ], user=user)

    @classmethod
    @transaction.atomic
    def creer_ecriture_facture_vente(cls, montant_ttc, montant_tva, libelle,
                                     compte_client_code, compte_produit_code,
                                     compte_tva_code=None, user=None):
        journal = cls.get_or_create_journal("VN", "Ventes", "VENTES")
        cc = cls.get_compte(compte_client_code)
        cp = cls.get_compte(compte_produit_code)
        ref = cls.generer_reference("FV")
        lignes = [
            {"compte": cc, "debit": montant_ttc, "libelle": libelle},
            {"compte": cp, "credit": montant_ttc - montant_tva, "libelle": libelle},
        ]
        if montant_tva > 0 and compte_tva_code:
            lignes.append({
                "compte": cls.get_compte(compte_tva_code),
                "credit": montant_tva, "libelle": f"TVA {libelle}",
            })
        return cls.creer_ecriture(ref, date.today(), libelle, journal, lignes, user=user)

    # ─── Achats / Fournisseurs ────────────────────────────────

    @classmethod
    @transaction.atomic
    def creer_ecriture_achat(cls, montant_ttc, montant_tva, montant_ht, libelle,
                             compte_charge_code, compte_fournisseur_code,
                             compte_tva_code=None, user=None):
        journal = cls.get_or_create_journal("AC", "Achats", "ACHATS")
        cch = cls.get_compte(compte_charge_code)
        cf = cls.get_compte(compte_fournisseur_code)
        ref = cls.generer_reference("AC")
        lignes = [
            {"compte": cch, "debit": montant_ht, "libelle": libelle},
            {"compte": cf, "credit": montant_ttc, "libelle": libelle},
        ]
        if montant_tva > 0 and compte_tva_code:
            lignes.append({
                "compte": cls.get_compte(compte_tva_code),
                "debit": montant_tva, "libelle": f"TVA {libelle}",
            })
        return cls.creer_ecriture(ref, date.today(), libelle, journal, lignes, user=user)

    @classmethod
    @transaction.atomic
    def creer_ecriture_charge(cls, compte_caisse_code, montant, libelle,
                              compte_charge_code, date_operation=None, user=None):
        if date_operation is None:
            date_operation = date.today()
        journal = cls._journal_paiement(compte_caisse_code)
        compte_caisse = cls.get_compte(compte_caisse_code)
        cc = cls.get_compte(compte_charge_code) or cls.get_compte("658")
        now = datetime.now()
        ref = cls.generer_reference("CH", now)
        return cls.creer_ecriture(ref, date_operation, libelle, journal, [
            {"compte": cc, "debit": montant, "libelle": libelle},
            {"compte": compte_caisse, "credit": montant, "libelle": f"Paiement {libelle}"},
        ], piece=f"DEP-{date_operation.strftime('%Y%m%d')}", user=user)

    # ─── Trésorerie ───────────────────────────────────────────

    @classmethod
    def _journal_paiement(cls, compte_caisse_code):
        if compte_caisse_code and str(compte_caisse_code).startswith("52"):
            return cls.get_or_create_journal("BQ", "Banque", "BANQUE")
        return cls.get_or_create_journal("CS", "Caisse", "CAISSE")

    @classmethod
    @transaction.atomic
    def creer_ecriture_transfert(cls, compte_source_code, compte_dest_code,
                                 montant, libelle, user=None):
        journal = cls.get_or_create_journal("TR", "Transferts", "CAISSE")
        ref = cls.generer_reference("TRF")
        return cls.creer_ecriture(ref, date.today(), libelle, journal, [
            {"compte": cls.get_compte(compte_dest_code), "debit": montant,
             "libelle": f"Transfert reçu"},
            {"compte": cls.get_compte(compte_source_code), "credit": montant,
             "libelle": f"Transfert émis"},
        ], user=user)

    @classmethod
    @transaction.atomic
    def creer_ecriture_depot_banque(cls, compte_caisse_code, montant, libelle, user=None):
        journal = cls.get_or_create_journal("BQ", "Banque", "BANQUE")
        ref = cls.generer_reference("DB")
        return cls.creer_ecriture(ref, date.today(), libelle, journal, [
            {"compte": cls.get_compte("521"), "debit": montant, "libelle": "Dépôt banque"},
            {"compte": cls.get_compte(compte_caisse_code), "credit": montant,
             "libelle": f"Dépôt depuis caisse"},
        ], user=user)

    @classmethod
    @transaction.atomic
    def creer_ecriture_retrait_banque(cls, compte_caisse_code, montant, libelle, user=None):
        journal = cls.get_or_create_journal("BQ", "Banque", "BANQUE")
        ref = cls.generer_reference("RB")
        return cls.creer_ecriture(ref, date.today(), libelle, journal, [
            {"compte": cls.get_compte(compte_caisse_code), "debit": montant,
             "libelle": f"Retrait banque vers caisse"},
            {"compte": cls.get_compte("521"), "credit": montant, "libelle": "Retrait banque"},
        ], user=user)

    # ─── Paie ─────────────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def creer_ecriture_salaire(cls, montant_brut, montant_net, montant_cnps,
                               montant_impot, montant_avances, libelle,
                               compte_caisse_code=None, user=None):
        journal = cls.get_or_create_journal("PA", "Paie", "CAISSE")
        caisse = cls.get_compte(compte_caisse_code) if compte_caisse_code else cls.get_compte("571")
        ref = cls.generer_reference("PAIE")
        lignes = [
            {"compte": cls.get_compte("661"), "debit": montant_brut, "libelle": libelle},
            {"compte": caisse, "credit": montant_net, "libelle": "Net à payer"},
        ]
        if montant_cnps > 0:
            lignes.append({"compte": cls.get_compte("431"), "credit": montant_cnps, "libelle": "CNPS"})
        if montant_impot > 0:
            lignes.append({"compte": cls.get_compte("447"), "credit": montant_impot, "libelle": "IRPP"})
        if montant_avances > 0:
            lignes.append({"compte": cls.get_compte("425"), "debit": montant_avances, "libelle": "Avances déduites"})
        return cls.creer_ecriture(ref, date.today(), libelle, journal, lignes, user=user)

    # ─── Stock ────────────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def creer_ecriture_entree_stock(cls, montant, libelle, compte_stock="31",
                                    compte_variation="6031", user=None):
        journal = cls.get_or_create_journal("ST", "Stock", "ACHATS")
        ref = cls.generer_reference("ES")
        return cls.creer_ecriture(ref, date.today(), libelle, journal, [
            {"compte": cls.get_compte(compte_stock), "debit": montant, "libelle": libelle},
            {"compte": cls.get_compte(compte_variation), "credit": montant, "libelle": libelle},
        ], user=user)

    @classmethod
    @transaction.atomic
    def creer_ecriture_sortie_stock(cls, montant, libelle, compte_charge="6032",
                                    compte_stock="31", user=None):
        journal = cls.get_or_create_journal("ST", "Stock", "ACHATS")
        ref = cls.generer_reference("SS")
        return cls.creer_ecriture(ref, date.today(), libelle, journal, [
            {"compte": cls.get_compte(compte_charge), "debit": montant, "libelle": libelle},
            {"compte": cls.get_compte(compte_stock), "credit": montant, "libelle": libelle},
        ], user=user)

    @classmethod
    @transaction.atomic
    def creer_ecriture_inventaire(cls, ecart, libelle, compte_stock="31",
                                  compte_charge="658", compte_produit="758", user=None):
        journal = cls.get_or_create_journal("ST", "Stock", "ACHATS")
        ref = cls.generer_reference("INV")
        if ecart >= 0:
            lignes = [
                {"compte": cls.get_compte(compte_stock), "debit": ecart, "libelle": libelle},
                {"compte": cls.get_compte(compte_produit), "credit": ecart, "libelle": libelle},
            ]
        else:
            e = -ecart
            lignes = [
                {"compte": cls.get_compte(compte_charge), "debit": e, "libelle": libelle},
                {"compte": cls.get_compte(compte_stock), "credit": e, "libelle": libelle},
            ]
        return cls.creer_ecriture(ref, date.today(), libelle, journal, lignes, user=user)

    # ─── Immobilisations ──────────────────────────────────────

    @classmethod
    @transaction.atomic
    def creer_ecriture_acquisition_immo(cls, montant, libelle, compte_immo_code,
                                        compte_tiers_code=None, compte_caisse_code=None, user=None):
        journal = cls.get_or_create_journal("INV", "Investissements", "ACHATS")
        ref = cls.generer_reference("ACQ")
        lignes = [
            {"compte": cls.get_compte(compte_immo_code), "debit": montant, "libelle": libelle},
        ]
        if compte_caisse_code:
            lignes.append({"compte": cls.get_compte(compte_caisse_code), "credit": montant, "libelle": libelle})
        elif compte_tiers_code:
            lignes.append({"compte": cls.get_compte(compte_tiers_code), "credit": montant, "libelle": libelle})
        else:
            lignes.append({"compte": cls.get_compte("404"), "credit": montant, "libelle": libelle})
        return cls.creer_ecriture(ref, date.today(), libelle, journal, lignes, user=user)

    @classmethod
    @transaction.atomic
    def creer_ecriture_amortissement(cls, plan, user=None):
        check_owned(plan.immobilisation, what="Immobilisation")
        immobilisation = plan.immobilisation
        journal = cls.get_or_create_journal("OD", "Opérations Diverses", "OD")
        ref = f"AMORT-{immobilisation.code}-{plan.periode.strftime('%Y%m')}"
        libelle = f"Amortissement {immobilisation.libelle} - {plan.periode.strftime('%m/%Y')}"
        ecriture = cls.creer_ecriture(ref, plan.periode, libelle, journal, [
            {"compte": immobilisation.compte_charge, "debit": plan.montant,
             "libelle": f"Dotation {immobilisation.libelle}"},
            {"compte": immobilisation.compte_amortissement, "credit": plan.montant,
             "libelle": f"Amortissement {immobilisation.libelle}"},
        ], exercice=cls.get_exercice(plan.periode), user=user)
        plan.ecriture_generee = True
        plan.ecriture_reference = ref
        plan.save(update_fields=["ecriture_generee", "ecriture_reference"])
        return ecriture

    # ─── Divers ───────────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def creer_ecriture_regularisation(cls, montant, libelle, compte_debit_code,
                                      compte_credit_code, user=None):
        journal = cls.get_or_create_journal("OD", "Opérations Diverses", "OD")
        ref = cls.generer_reference("RG")
        return cls.creer_ecriture(ref, date.today(), libelle, journal, [
            {"compte": cls.get_compte(compte_debit_code), "debit": montant, "libelle": libelle},
            {"compte": cls.get_compte(compte_credit_code), "credit": montant, "libelle": libelle},
        ], user=user)

    @classmethod
    @transaction.atomic
    def creer_ecriture_cloture_exercice(cls, exercice, resultat, user=None):
        check_owned(exercice, what="Exercice")
        raise ValidationError(
            "Génération d'écriture de clôture désactivée jusqu'à "
            "la validation des règles SYSCOHADA."
        )
