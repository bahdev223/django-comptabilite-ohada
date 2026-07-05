from decimal import Decimal
from datetime import date, datetime

from django.db import transaction
from django.utils import timezone

from ..models import EcritureComptable, LigneEcritureComptable, JournalComptable
from ..models import CompteComptable, ExerciceComptable
from ..signals.ecriture import ecriture_validee


class EcritureService:
    """Service central de création d'écritures comptables — point d'entrée unique."""

    # ─── Helpers ──────────────────────────────────────────────

    @classmethod
    def get_exercice(cls, date_operation=None):
        if date_operation is None:
            date_operation = date.today()
        exercice = ExerciceComptable.objects.filter(
            date_debut__lte=date_operation,
            date_fin__gte=date_operation,
            cloture=False,
        ).first()
        if not exercice:
            exercice = ExerciceComptable.objects.filter(cloture=False).first()
        return exercice

    @classmethod
    def get_or_create_journal(cls, code, libelle, type_journal):
        journal, _ = JournalComptable.objects.get_or_create(
            code=code,
            defaults={"libelle": libelle, "type_journal": type_journal, "actif": True},
        )
        return journal

    @classmethod
    def get_compte(cls, code_or_id):
        if code_or_id is None:
            return None
        if isinstance(code_or_id, int):
            return CompteComptable.objects.filter(id=code_or_id, actif=True).first()
        compte = CompteComptable.objects.filter(code=str(code_or_id), actif=True).first()
        if compte:
            return compte
        if isinstance(code_or_id, str) and code_or_id.isdigit():
            return CompteComptable.objects.filter(id=int(code_or_id), actif=True).first()
        return None

    @classmethod
    def get_compte_par_type_caisse(cls, type_caisse):
        mapping = {"ESPECES": "571", "BANQUE": "521", "MOBILE_MONEY": "581"}
        code = mapping.get(type_caisse, "571")
        return cls.get_compte(code)

    @classmethod
    def generer_reference(cls, prefix, dt=None, seq=None):
        if dt is None:
            dt = datetime.now()
        if seq:
            return f"{prefix}-{dt.strftime('%Y%m%d')}-{seq}"
        return f"{prefix}-{dt.strftime('%Y%m%d%H%M%S')}"

    @classmethod
    @transaction.atomic
    def creer_ecriture(cls, reference, date_ecriture, libelle, journal, lignes,
                       exercice=None, piece=None, validee=True, user=None):
        if exercice is None:
            exercice = cls.get_exercice(date_ecriture)

        ecriture = EcritureComptable.objects.create(
            reference=reference,
            date_ecriture=date_ecriture,
            libelle=libelle,
            journal=journal,
            piece=piece,
            exercice=exercice,
            validee=validee,
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
        ref = cls.generer_reference("CH", date_operation)
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
        journal = cls.get_or_create_journal("CL", "Clôture", "OD")
        ref = f"RES-{exercice.code}"
        libelle = f"Affectation résultat exercice {exercice.code}"
        if resultat >= 0:
            lignes = [
                {"compte": cls.get_compte("129"), "debit": resultat,
                 "libelle": f"Bénéfice {exercice.code}"},
                {"compte": cls.get_compte("101"), "credit": resultat,
                 "libelle": f"Capital - report bénéfice {exercice.code}"},
            ]
        else:
            r = abs(resultat)
            lignes = [
                {"compte": cls.get_compte("101"), "debit": r,
                 "libelle": f"Imputation perte {exercice.code}"},
                {"compte": cls.get_compte("129"), "credit": r,
                 "libelle": f"Perte {exercice.code}"},
            ]
        return cls.creer_ecriture(ref, exercice.date_fin, libelle, journal, lignes,
                                  exercice=exercice, user=user)
