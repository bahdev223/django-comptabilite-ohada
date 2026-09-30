from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import RequestFactory, TestCase

from comptabilite_ohada.authentication import AccountingAPIKeyAuthentication
from comptabilite_ohada.models import (
    ApplicationClienteComptable,
    CompteComptable,
    ConfigurationComptable,
    EcritureComptable,
    ExerciceComptable,
    Immobilisation,
    OrganisationComptable,
    RegleEvenementComptable,
)
from comptabilite_ohada.services.amortissement_service import AmortissementService
from comptabilite_ohada.services.bilan_service import BilanService
from comptabilite_ohada.services.ecriture_service import EcritureService
from comptabilite_ohada.services.evenement_service import EvenementService
from comptabilite_ohada.services.exercice_service import ExerciceService
from comptabilite_ohada.services.initialisation_service import InitialisationService


class ReleaseAccountingBase(TestCase):
    entreprise_id = "ENT-READY"

    def setUp(self):
        InitialisationService.charger_plan_comptable(
            force=True, entreprise_id=self.entreprise_id
        )
        InitialisationService.initialiser_journaux(self.entreprise_id)
        self.exercice = ExerciceComptable.objects.create(
            code="2026",
            date_debut=date(2026, 1, 1),
            date_fin=date(2026, 12, 31),
            entreprise_id=self.entreprise_id,
        )

    def compte(self, code):
        return CompteComptable.objects.get(
            entreprise_id=self.entreprise_id, code=code
        )


class StarterChartReadinessTest(ReleaseAccountingBase):
    def test_comptes_requis_par_le_moteur_sont_presents(self):
        requis = {
            "101", "131", "139", "31", "401", "404", "411", "425",
            "431", "443", "445", "447", "521", "552", "571", "585",
            "601", "6031", "6032", "658", "661", "701", "706", "758",
            "81", "82", "83", "84", "89",
        }
        presents = set(
            CompteComptable.objects.filter(
                entreprise_id=self.entreprise_id,
                code__in=requis,
            ).values_list("code", flat=True)
        )
        self.assertEqual(presents, requis)
        self.assertIn("bénéfice", self.compte("131").libelle.lower())
        self.assertEqual(self.compte("552").solde_normal, "DEBIT")


class OperationalEntryReadinessTest(ReleaseAccountingBase):
    def test_paie_avec_avance_est_equilibree(self):
        ecriture = EcritureService.creer_ecriture_salaire(
            montant_brut=Decimal("100000"),
            montant_net=Decimal("80000"),
            montant_cnps=Decimal("10000"),
            montant_impot=Decimal("5000"),
            montant_avances=Decimal("5000"),
            libelle="Paie septembre",
            entreprise_id=self.entreprise_id,
            date_operation=date(2026, 9, 30),
        )
        self.assertTrue(ecriture.est_equilibree)
        self.assertEqual(ecriture.total_debit, Decimal("100000"))
        self.assertEqual(ecriture.total_credit, Decimal("100000"))

    def test_facture_vente_tva_est_equilibree(self):
        ecriture = EcritureService.creer_ecriture_facture_vente(
            montant_ttc=Decimal("118000"),
            montant_tva=Decimal("18000"),
            libelle="Facture client",
            compte_client_code="411",
            compte_produit_code="706",
            compte_tva_code="443",
            entreprise_id=self.entreprise_id,
            date_operation=date(2026, 9, 30),
        )
        self.assertTrue(ecriture.est_equilibree)

    def test_facture_sans_compte_tva_prend_le_ttc_en_produit(self):
        ecriture = EcritureService.creer_ecriture_facture_vente(
            montant_ttc=Decimal("118000"),
            montant_tva=Decimal("18000"),
            libelle="Facture sans ventilation TVA",
            compte_client_code="411",
            compte_produit_code="706",
            compte_tva_code=None,
            entreprise_id=self.entreprise_id,
            date_operation=date(2026, 9, 30),
        )
        self.assertTrue(ecriture.est_equilibree)


class ClosingReadinessTest(ReleaseAccountingBase):
    def test_cloture_solde_6_7_8_et_conserve_resultat_historique(self):
        journal = EcritureService.get_or_create_journal(
            "OD", "Opérations diverses", "OD", self.entreprise_id
        )
        EcritureService.creer_ecriture(
            reference="OPS-1",
            date_ecriture=date(2026, 6, 1),
            libelle="Activité et HAO",
            journal=journal,
            exercice=self.exercice,
            entreprise_id=self.entreprise_id,
            lignes=[
                {"compte": self.compte("601"), "debit": Decimal("1000")},
                {"compte": self.compte("701"), "credit": Decimal("1500")},
                {"compte": self.compte("83"), "debit": Decimal("100")},
                {"compte": self.compte("84"), "credit": Decimal("50")},
                {"compte": self.compte("571"), "debit": Decimal("550")},
                {"compte": self.compte("571"), "credit": Decimal("1000")},
            ],
        )
        avant = BilanService.compte_resultat(
            exercice=self.exercice, entreprise_id=self.entreprise_id
        )
        self.assertEqual(avant["resultat_net"], Decimal("450"))

        ExerciceService.cloturer(self.exercice)
        cloture = EcritureComptable.objects.get(
            entreprise_id=self.entreprise_id,
            source_type="fiscal_closure",
            source_id=str(self.exercice.pk),
        )
        self.assertTrue(cloture.est_equilibree)
        self.assertTrue(
            cloture.lignes.filter(compte__code="131", credit=Decimal("450")).exists()
        )

        apres = BilanService.compte_resultat(
            exercice=self.exercice, entreprise_id=self.entreprise_id
        )
        self.assertEqual(apres["resultat_net"], Decimal("450"))


class EventRetryReadinessTest(ReleaseAccountingBase):
    def test_evenement_generique_en_erreur_peut_etre_rejoue(self):
        RegleEvenementComptable.objects.create(
            entreprise_id=self.entreprise_id,
            type_evenement="project.expense.created",
            code_regle="ECRITURE_GENERIQUE",
        )
        event, created = EvenementService.recevoir(
            entreprise_id=self.entreprise_id,
            type_evenement="project.expense.created",
            source_system="saheltech-platform",
            source_type="expense",
            source_id="EXP-1",
            idempotency_key="expense:EXP-1:v1",
            payload={
                "date": "2026-09-30",
                "libelle": "Dépense projet",
                "journal_code": "OD",
                "lignes": [
                    {"compte": "99991", "debit": "5000"},
                    {"compte": "552", "credit": "5000"},
                ],
                "dimensions": {"PROJECT": "PROJ-1"},
            },
        )
        self.assertTrue(created)
        self.assertEqual(event.statut, "ERREUR")
        self.assertIsNone(event.ecriture)

        CompteComptable.objects.create(
            entreprise_id=self.entreprise_id,
            code="99991",
            libelle="Compte métier configuré",
            nature="CHARGE",
            sens="DEBIT",
            categorie="resultat",
        )
        event = EvenementService.retraiter(event)
        self.assertEqual(event.statut, "TRAITE")
        self.assertIsNotNone(event.ecriture)
        self.assertTrue(event.ecriture.est_equilibree)


class AmortizationReadinessTest(ReleaseAccountingBase):
    def test_plan_mensuel_est_exact_sur_douze_mois(self):
        immo = Immobilisation.objects.create(
            entreprise_id=self.entreprise_id,
            code="IMMO-1",
            libelle="Véhicule",
            type_immobilisation="CORPORELLE",
            date_acquisition=date(2026, 1, 15),
            valeur_originale=Decimal("120000"),
            valeur_residuelle=Decimal("0"),
            duree_ans=1,
            compte_immobilisation=self.compte("245"),
            compte_amortissement=self.compte("28"),
            compte_charge=self.compte("68"),
        )
        plan = list(AmortissementService.generer_plan(immo))
        self.assertEqual(len(plan), 12)
        self.assertEqual(plan[0].periode, date(2026, 1, 1))
        self.assertEqual(plan[-1].periode, date(2026, 12, 1))
        self.assertEqual(sum((p.montant for p in plan), Decimal("0")), Decimal("120000"))
        self.assertEqual(plan[-1].amortissement_cumule, Decimal("120000"))


class FiscalYearAndConfigReadinessTest(TestCase):
    def test_exercices_ne_peuvent_pas_se_chevaucher(self):
        ExerciceComptable.objects.create(
            code="2026",
            date_debut=date(2026, 1, 1),
            date_fin=date(2026, 12, 31),
            entreprise_id="A",
        )
        with self.assertRaises(ValidationError):
            ExerciceComptable.objects.create(
                code="2026-BIS",
                date_debut=date(2026, 7, 1),
                date_fin=date(2027, 6, 30),
                entreprise_id="A",
            )

    def test_une_seule_configuration_par_entreprise(self):
        ConfigurationComptable.objects.create(entreprise_id="A", nom="A")
        with self.assertRaises(IntegrityError):
            ConfigurationComptable.objects.create(entreprise_id="A", nom="A bis")


class MachineAuthenticationReadinessTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.org = OrganisationComptable.objects.create(
            code="ENT-API", nom="Entreprise API"
        )

    def test_cle_api_est_hashée_et_authentifie_le_tenant(self):
        app, secret = ApplicationClienteComptable.generer_cle(
            entreprise=self.org,
            nom="saheltech-platform",
            scopes=["accounting.read", "accounting.events.write"],
        )
        self.assertNotEqual(app.secret_hash, secret)
        request = self.factory.get("/", HTTP_X_API_KEY=secret)
        principal, auth = AccountingAPIKeyAuthentication().authenticate(request)
        self.assertEqual(principal.entreprise_id, "ENT-API")
        self.assertIn("accounting.events.write", principal.api_scopes)
        self.assertEqual(auth.pk, app.pk)
