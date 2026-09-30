from decimal import Decimal
from datetime import date, datetime

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date

from ..models import EcritureComptable, LigneEcritureComptable, JournalComptable
from ..models import CompteComptable, ExerciceComptable
from ..signals.ecriture import ecriture_validee
from django.core.exceptions import ValidationError


class EcritureService:
    """Service central de création d'écritures comptables — point d'entrée unique."""

    # ─── Helpers ──────────────────────────────────────────────

    @classmethod
    def get_exercice(cls, date_operation=None, entreprise_id=""):
        if date_operation is None:
            date_operation = date.today()
        return ExerciceComptable.objects.filter(
            entreprise_id=entreprise_id or "",
            date_debut__lte=date_operation,
            date_fin__gte=date_operation,
            cloture=False,
        ).first()

    @classmethod
    def get_or_create_journal(cls, code, libelle, type_journal, entreprise_id=""):
        journal, _ = JournalComptable.objects.get_or_create(
            entreprise_id=entreprise_id or "",
            code=code,
            defaults={"libelle": libelle, "type_journal": type_journal, "actif": True},
        )
        return journal

    @classmethod
    def get_compte(cls, code_or_id, entreprise_id=""):
        if code_or_id is None:
            return None
        scope = {"entreprise_id": entreprise_id or "", "actif": True}
        if isinstance(code_or_id, int):
            return CompteComptable.objects.filter(id=code_or_id, **scope).first()
        compte = CompteComptable.objects.filter(code=str(code_or_id), **scope).first()
        if compte:
            return compte
        if isinstance(code_or_id, str) and code_or_id.isdigit():
            return CompteComptable.objects.filter(id=int(code_or_id), **scope).first()
        return None

    @classmethod
    def get_compte_par_type_caisse(cls, type_caisse, entreprise_id=""):
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
                       exercice=None, piece=None, validee=True, user=None,
                       entreprise_id=None, source_system="", source_type="",
                       source_id="", source_reference="", idempotency_key=None,
                       metadata=None, reversal_of=None):
        if isinstance(date_ecriture, datetime):
            date_ecriture = date_ecriture.date()
        elif isinstance(date_ecriture, str):
            parsed_date = parse_date(date_ecriture)
            if parsed_date is None:
                raise ValidationError(f"Date d'écriture invalide : {date_ecriture}")
            date_ecriture = parsed_date

        if entreprise_id is None:
            entreprise_id = (
                getattr(exercice, "entreprise_id", None)
                or getattr(journal, "entreprise_id", "")
                or ""
            )
        if idempotency_key:
            existante = EcritureComptable.objects.filter(
                entreprise_id=entreprise_id or "",
                idempotency_key=idempotency_key,
            ).first()
            if existante:
                return existante

        if exercice is None:
            exercice = cls.get_exercice(date_ecriture, entreprise_id=entreprise_id)
        # get_exercice rend None quand aucun exercice ouvert ne couvre la
        # date. L'ecriture partait alors avec exercice=None et l'echec
        # remontait en IntegrityError depuis la base, apres qu'une
        # operation de tresorerie avait deja pu etre enregistree. On
        # refuse ici, avec un message qui dit quoi faire.
        if exercice is None:
            raise ValidationError(
                "Aucun exercice comptable ouvert ne couvre la date "
                f"{date_ecriture}. Ouvrez un exercice avant d'enregistrer "
                "des ecritures."
            )
        if exercice.cloture:
            raise ValidationError(f"L'exercice {exercice.code} est clôturé.")
        date_debut = parse_date(exercice.date_debut) if isinstance(exercice.date_debut, str) else exercice.date_debut
        date_fin = parse_date(exercice.date_fin) if isinstance(exercice.date_fin, str) else exercice.date_fin
        if not (date_debut <= date_ecriture <= date_fin):
            raise ValidationError(
                f"La date {date_ecriture} est hors de l'exercice {exercice.code} "
                f"({date_debut} → {date_fin})."
            )
        if (exercice.entreprise_id or "") != (entreprise_id or ""):
            raise ValidationError("L'exercice n'appartient pas à la même entreprise que l'écriture.")
        if (journal.entreprise_id or "") != (entreprise_id or ""):
            raise ValidationError("Le journal n'appartient pas à la même entreprise que l'écriture.")

        # Une ecriture doit etre equilibree : c'est la regle fondatrice de
        # la partie double. Elle etait exposee par est_equilibree mais
        # jamais appliquee, si bien qu'une ecriture fausse pouvait etre
        # enregistree ET marquee validee. On refuse avant toute creation,
        # la transaction n'ayant alors rien a annuler.
        total_debit = sum(
            (Decimal(str(ligne.get("debit", 0) or 0)) for ligne in lignes), Decimal("0.00")
        )
        total_credit = sum(
            (Decimal(str(ligne.get("credit", 0) or 0)) for ligne in lignes), Decimal("0.00")
        )
        if total_debit != total_credit:
            raise ValidationError(
                f"Ecriture desequilibree : debit {total_debit}, credit {total_credit}. "
                f"L'ecart est de {abs(total_debit - total_credit)}."
            )
        if total_debit == 0:
            raise ValidationError("Une ecriture sans montant ne peut pas etre enregistree.")

        # get_compte rend None quand le code n'existe pas au plan comptable.
        # La ligne partait alors avec compte=None et se faisait rejeter par
        # la contrainte NOT NULL, bien apres le point ou l'on aurait pu
        # expliquer le probleme. On nomme le compte manquant.
        for position, ligne in enumerate(lignes, start=1):
            compte = ligne.get("compte")
            if compte is None:
                raise ValidationError(
                    f"Ligne {position} de l'ecriture « {libelle} » : compte "
                    "comptable introuvable. Verifiez que le code existe et "
                    "qu'il est actif au plan comptable."
                )
            if (compte.entreprise_id or "") != (entreprise_id or ""):
                raise ValidationError(
                    f"Ligne {position} : le compte {compte.code} appartient à une autre entreprise."
                )

        ecriture = EcritureComptable.objects.create(
            reference=reference,
            date_ecriture=date_ecriture,
            libelle=libelle,
            journal=journal,
            piece=piece,
            exercice=exercice,
            validee=validee,
            created_by=user.username if hasattr(user, "username") and user else str(user or ""),
            validated_by=(user.username if hasattr(user, "username") and user else str(user or "")) if validee else None,
            date_validation=timezone.now() if validee else None,
            entreprise_id=entreprise_id or "",
            source_system=source_system or "",
            source_type=source_type or "",
            source_id=str(source_id or ""),
            source_reference=source_reference or "",
            idempotency_key=idempotency_key or None,
            metadata=metadata or {},
            reversal_of=reversal_of,
        )

        for ligne in lignes:
            ligne_obj = LigneEcritureComptable.objects.create(
                ecriture=ecriture,
                compte=ligne["compte"],
                debit=ligne.get("debit", Decimal("0.00")),
                credit=ligne.get("credit", Decimal("0.00")),
                libelle=ligne.get("libelle", libelle),
            )
            dimensions = ligne.get("dimensions") or {}
            if dimensions:
                from .analytique_service import AnalytiqueService
                AnalytiqueService.affecter_ligne(ligne_obj, dimensions)

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
                             compte_produit_code, user=None, entreprise_id="", piece=None):
        journal = cls.get_or_create_journal("VN", "Ventes", "VENTES", entreprise_id)
        compte_caisse = cls.get_compte(compte_caisse_code, entreprise_id)
        compte_produit = cls.get_compte(compte_produit_code, entreprise_id)
        ref = cls.generer_reference("VN")
        return cls.creer_ecriture(ref, date.today(), libelle, journal, [
            {"compte": compte_caisse, "debit": montant, "libelle": "Encaissement vente"},
            {"compte": compte_produit, "credit": montant, "libelle": libelle},
        ], user=user, piece=piece, entreprise_id=entreprise_id)

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
                              compte_charge_code, date_operation=None, user=None,
                              entreprise_id="", piece=None):
        if date_operation is None:
            date_operation = date.today()
        journal = cls._journal_paiement(compte_caisse_code, entreprise_id)
        compte_caisse = cls.get_compte(compte_caisse_code, entreprise_id)
        cc = cls.get_compte(compte_charge_code, entreprise_id) or cls.get_compte("658", entreprise_id)
        now = datetime.now()
        ref = cls.generer_reference("CH", now)
        return cls.creer_ecriture(ref, date_operation, libelle, journal, [
            {"compte": cc, "debit": montant, "libelle": libelle},
            {"compte": compte_caisse, "credit": montant, "libelle": f"Paiement {libelle}"},
        ], piece=piece or f"DEP-{date_operation.strftime('%Y%m%d')}", user=user,
           entreprise_id=entreprise_id)

    # ─── Trésorerie ───────────────────────────────────────────

    @classmethod
    def _journal_paiement(cls, compte_caisse_code, entreprise_id=""):
        if compte_caisse_code and str(compte_caisse_code).startswith("52"):
            return cls.get_or_create_journal("BQ", "Banque", "BANQUE", entreprise_id)
        return cls.get_or_create_journal("CS", "Caisse", "CAISSE", entreprise_id)

    @classmethod
    @transaction.atomic
    def creer_ecriture_transfert(cls, compte_source_code, compte_dest_code,
                                 montant, libelle, user=None, entreprise_id="", piece=None):
        journal = cls.get_or_create_journal("TR", "Transferts", "CAISSE", entreprise_id)
        ref = cls.generer_reference("TRF")
        return cls.creer_ecriture(ref, date.today(), libelle, journal, [
            {"compte": cls.get_compte(compte_dest_code, entreprise_id), "debit": montant,
             "libelle": f"Transfert reçu"},
            {"compte": cls.get_compte(compte_source_code, entreprise_id), "credit": montant,
             "libelle": f"Transfert émis"},
        ], user=user, piece=piece, entreprise_id=entreprise_id)

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
        entreprise_id = immobilisation.entreprise_id or ""
        journal = cls.get_or_create_journal("OD", "Opérations Diverses", "OD", entreprise_id)
        ref = f"AMORT-{immobilisation.code}-{plan.periode.strftime('%Y%m')}"
        libelle = f"Amortissement {immobilisation.libelle} - {plan.periode.strftime('%m/%Y')}"
        ecriture = cls.creer_ecriture(ref, plan.periode, libelle, journal, [
            {"compte": immobilisation.compte_charge, "debit": plan.montant,
             "libelle": f"Dotation {immobilisation.libelle}"},
            {"compte": immobilisation.compte_amortissement, "credit": plan.montant,
             "libelle": f"Amortissement {immobilisation.libelle}"},
        ], exercice=cls.get_exercice(plan.periode, entreprise_id), user=user,
           entreprise_id=entreprise_id)
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
        entreprise_id = exercice.entreprise_id or ""
        journal = cls.get_or_create_journal("CL", "Clôture", "OD", entreprise_id)
        ref = cls.generer_reference(f"RES-{exercice.code}")
        libelle = f"Affectation résultat exercice {exercice.code}"
        if resultat >= 0:
            lignes = [
                {"compte": cls.get_compte("129", entreprise_id), "debit": resultat,
                 "libelle": f"Bénéfice {exercice.code}"},
                {"compte": cls.get_compte("101", entreprise_id), "credit": resultat,
                 "libelle": f"Capital - report bénéfice {exercice.code}"},
            ]
        else:
            r = abs(resultat)
            lignes = [
                {"compte": cls.get_compte("101", entreprise_id), "debit": r,
                 "libelle": f"Imputation perte {exercice.code}"},
                {"compte": cls.get_compte("129", entreprise_id), "credit": r,
                 "libelle": f"Perte {exercice.code}"},
            ]
        return cls.creer_ecriture(
            ref, exercice.date_fin, libelle, journal, lignes,
            exercice=exercice,
            user=user,
            entreprise_id=entreprise_id,
            source_system="comptabilite_ohada",
            source_type="fiscal_closure",
            source_id=str(exercice.pk),
            source_reference=exercice.code,
        )
