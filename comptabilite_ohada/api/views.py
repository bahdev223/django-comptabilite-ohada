from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes as api_permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework import serializers
from django.conf import settings
from ..permissions import AccountingTenantPermission
from ..tenant import resolve_entreprise_id
from django_filters import rest_framework as filters
from django.db.models import Sum, Q
from django.utils import timezone

from ..models import (
    CompteComptable, EcritureComptable, LigneEcritureComptable,
    JournalComptable, ExerciceComptable, ConfigurationComptable,
    Immobilisation, PlanAmortissement,
    DimensionAnalytique, ValeurAnalytique,
    EvenementMetier, RegleEvenementComptable,
    OrganisationComptable,
    ReleveBancaire,
)
from ..services.ecriture_service import EcritureService
from ..services.journal_service import BalanceService, GrandLivreService
from ..services.bilan_service import BilanService
from ..services.exercice_service import ExerciceService, ValidationService
from ..services.amortissement_service import AmortissementService
from ..services.analytique_service import AnalytiqueService
from ..services.evenement_service import EvenementService, IdempotencyConflict
from ..sqlite_busy import AccountingBusy
from .exceptions import AccountingServiceUnavailable, accounting_storage_operation
from ..services.rapprochement_service import RapprochementService
from .serializers import (
    CompteComptableSerializer, EcritureComptableSerializer,
    EcritureCreateSerializer, JournalComptableSerializer,
    ExerciceComptableSerializer, ConfigurationComptableSerializer,
    ImmobilisationSerializer, PlanAmortissementSerializer,
    DimensionAnalytiqueSerializer, ValeurAnalytiqueSerializer,
    RegleEvenementComptableSerializer, EvenementMetierSerializer,
    EvenementIngestSerializer,
    OrganisationComptableSerializer,
    ReleveBancaireSerializer,
    LigneReleveBancaireSerializer,
)


@api_view(["GET"])
@api_permission_classes([AllowAny])
def health_view(request):
    return Response({
        "status": "ok",
        "service": "django-comptabilite-ohada",
        "api": "v1",
    })


@api_view(["GET"])
@api_permission_classes([IsAuthenticated, AccountingTenantPermission])
@accounting_storage_operation
def analytic_costs_view(request):
    reserved = {"date_debut", "date_fin", "format"}
    dimensions = {
        key.upper(): value
        for key, value in request.query_params.items()
        if key not in reserved and value not in (None, "")
    }
    if not dimensions:
        raise DRFValidationError(
            "Fournissez au moins une dimension, par exemple PROJECT=PRJ-001."
        )
    entreprise_id = resolve_entreprise_id(request)
    dates = {}
    for field in ("date_debut", "date_fin"):
        if field in request.query_params:
            dates[field] = serializers.DateField().run_validation(request.query_params[field])
    if dates.get("date_debut") and dates.get("date_fin") and dates["date_debut"] > dates["date_fin"]:
        raise DRFValidationError("La date de début doit précéder la date de fin.")
    result = AnalytiqueService.calculer_couts(
        entreprise_id=entreprise_id,
        dimensions=dimensions,
        **dates,
    )
    # Les montants HTTP sont des décimaux textuels, sans perte de précision.
    for field in ("total_cost", "allocated_debit", "allocated_credit"):
        result[field] = str(result[field])
    devise = ConfigurationComptable.objects.filter(entreprise_id=entreprise_id).values_list("devise", flat=True).first()
    result["currency"] = devise or getattr(settings, "COMPTABILITE_OHADA", {}).get("DEVISE_PAR_DEFAUT", "FCFA")
    return Response(result)


class EntrepriseScopedViewSetMixin:
    """Scope les ressources comptables sur l'entreprise portée par l'utilisateur."""

    def get_entreprise_id(self):
        return resolve_entreprise_id(self.request)

    def get_queryset(self):
        return super().get_queryset().filter(entreprise_id=self.get_entreprise_id())

    def perform_create(self, serializer):
        serializer.save(entreprise_id=self.get_entreprise_id())

    def perform_update(self, serializer):
        serializer.save(entreprise_id=self.get_entreprise_id())


class OrganisationComptableViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = OrganisationComptableSerializer
    search_fields = ["code", "nom"]

    def get_queryset(self):
        user = self.request.user
        if getattr(user, "is_superuser", False):
            return OrganisationComptable.objects.filter(actif=True)
        direct = str(getattr(user, "entreprise_id", "") or "")
        if direct:
            return OrganisationComptable.objects.filter(code=direct, actif=True)
        return OrganisationComptable.objects.filter(
            actif=True,
            acces_utilisateurs__user=user,
            acces_utilisateurs__actif=True,
        ).distinct()


class CompteComptableViewSet(EntrepriseScopedViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, AccountingTenantPermission]
    queryset = CompteComptable.objects.all()
    serializer_class = CompteComptableSerializer
    filterset_fields = ["code", "nature", "type_compte", "categorie", "actif", "entreprise_id"]
    search_fields = ["code", "libelle"]

    @action(detail=True, methods=["get"])
    def solde(self, request, pk=None):
        compte = self.get_object()
        exercice_id = request.query_params.get("exercice")
        exercice = None
        if exercice_id:
            exercice = ExerciceComptable.objects.filter(
                pk=exercice_id,
                entreprise_id=self.get_entreprise_id(),
            ).first()
            if exercice is None:
                raise DRFValidationError("Exercice introuvable pour cette entreprise.")
        return Response({
            "solde": BalanceService.solde_compte(
                compte, exercice=exercice
            )
        })


class EcritureComptableViewSet(EntrepriseScopedViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, AccountingTenantPermission]
    queryset = EcritureComptable.objects.prefetch_related("lignes__compte").all()
    filterset_fields = ["validee", "journal", "exercice", "entreprise_id"]
    search_fields = ["reference", "libelle"]

    def get_serializer_class(self):
        if self.action == "create":
            return EcritureCreateSerializer
        return EcritureComptableSerializer

    def _resolve_exercice(self, exercice_id):
        if not exercice_id:
            return None
        exercice = ExerciceComptable.objects.filter(
            pk=exercice_id,
            entreprise_id=self.get_entreprise_id(),
        ).first()
        if exercice is None:
            raise DRFValidationError(
                "Exercice introuvable pour cette entreprise."
            )
        return exercice

    def _ensure_mutable(self, ecriture):
        if ecriture.validee:
            raise DRFValidationError(
                "Une écriture validée est immuable. Utilisez une contre-passation."
            )

    def update(self, request, *args, **kwargs):
        self._ensure_mutable(self.get_object())
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._ensure_mutable(self.get_object())
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._ensure_mutable(self.get_object())
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def valider(self, request, pk=None):
        ecriture = self.get_object()
        if ecriture.validee:
            return Response({"error": "Déjà validée"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            ValidationService.valider_ecriture(ecriture, request.user)
            return Response({"status": "validée"})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def annuler(self, request, pk=None):
        ecriture = self.get_object()
        try:
            ValidationService.annuler_ecriture(ecriture, request.user)
            return Response({"status": "annulée"})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["get"])
    def balance(self, request):
        exercice_id = request.query_params.get("exercice")
        service = BalanceService()
        entreprise_id = self.get_entreprise_id()
        exercice = self._resolve_exercice(exercice_id)
        data = service.balance(
            exercice=exercice, entreprise_id=entreprise_id
        )
        payload = []
        for item in data:
            compte = item["compte"]
            payload.append({
                "compte": {
                    "id": compte.pk,
                    "code": compte.code,
                    "libelle": compte.libelle,
                },
                "total_debit": item["total_debit"],
                "total_credit": item["total_credit"],
                "solde": item["solde"],
                "solde_debiteur": item["solde_debiteur"],
                "solde_crediteur": item["solde_crediteur"],
            })
        return Response(payload)

    @action(detail=False, methods=["get"])
    def grand_livre(self, request):
        compte_code = request.query_params.get("compte")
        exercice_id = request.query_params.get("exercice")
        service = GrandLivreService()
        entreprise_id = self.get_entreprise_id()
        exercice = self._resolve_exercice(exercice_id)
        data = service.grand_livre(
            compte_code=compte_code,
            exercice=exercice,
            entreprise_id=entreprise_id,
        )
        return Response([
            {
                "date": item["date"],
                "reference": item["reference"],
                "libelle": item["libelle"],
                "compte": {
                    "id": item["compte"].pk,
                    "code": item["compte"].code,
                    "libelle": item["compte"].libelle,
                },
                "debit": item["debit"],
                "credit": item["credit"],
            }
            for item in data
        ])

    @action(detail=False, methods=["get"])
    def bilan(self, request):
        exercice_id = request.query_params.get("exercice")
        service = BilanService()
        entreprise_id = self.get_entreprise_id()
        exercice = self._resolve_exercice(exercice_id)
        bilan = service.bilan(exercice=exercice, entreprise_id=entreprise_id)
        return Response(bilan)

    @action(detail=False, methods=["get"])
    def compte_resultat(self, request):
        exercice_id = request.query_params.get("exercice")
        service = BilanService()
        entreprise_id = self.get_entreprise_id()
        exercice = self._resolve_exercice(exercice_id)
        resultat = service.compte_resultat(exercice=exercice, entreprise_id=entreprise_id)
        return Response(resultat)


class JournalComptableViewSet(EntrepriseScopedViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, AccountingTenantPermission]
    queryset = JournalComptable.objects.all()
    serializer_class = JournalComptableSerializer
    filterset_fields = ["code", "actif"]
    search_fields = ["code", "libelle"]

    @action(detail=True, methods=["get"])
    def ecritures(self, request, pk=None):
        journal = self.get_object()
        ecritures = EcritureComptable.objects.filter(journal=journal)
        page = self.paginate_queryset(ecritures)
        if page is not None:
            serializer = EcritureComptableSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = EcritureComptableSerializer(ecritures, many=True)
        return Response(serializer.data)


class ExerciceComptableViewSet(EntrepriseScopedViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, AccountingTenantPermission]
    queryset = ExerciceComptable.objects.all()
    serializer_class = ExerciceComptableSerializer
    filterset_fields = ["cloture", "entreprise_id"]
    search_fields = ["code"]

    @action(detail=True, methods=["post"])
    def cloturer(self, request, pk=None):
        exercice = self.get_object()
        try:
            ExerciceService.cloturer(exercice, request.user)
            return Response({"status": "clôturé"})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def rouvrir(self, request, pk=None):
        exercice = self.get_object()
        try:
            ExerciceService.rouvrir(exercice, request.user)
            return Response({"status": "rouvert"})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ConfigurationComptableViewSet(EntrepriseScopedViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, AccountingTenantPermission]
    queryset = ConfigurationComptable.objects.all()
    serializer_class = ConfigurationComptableSerializer


class ReleveBancaireViewSet(EntrepriseScopedViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, AccountingTenantPermission]
    queryset = ReleveBancaire.objects.prefetch_related("lignes").all()
    serializer_class = ReleveBancaireSerializer
    filterset_fields = ["compte_comptable_code", "statut"]
    search_fields = ["compte_comptable_code"]

    def _ensure_mutable(self, releve):
        if releve.statut == "RAPPROCHE":
            raise DRFValidationError("Un relevé rapproché est verrouillé.")

    def update(self, request, *args, **kwargs):
        self._ensure_mutable(self.get_object())
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._ensure_mutable(self.get_object())
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._ensure_mutable(self.get_object())
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="lignes")
    def ajouter_ligne(self, request, pk=None):
        releve = self.get_object()
        serializer = LigneReleveBancaireSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ligne = RapprochementService.ajouter_ligne(
            releve=releve,
            date_operation=serializer.validated_data["date_operation"],
            libelle=serializer.validated_data["libelle"],
            montant=serializer.validated_data["montant"],
            sens=serializer.validated_data["sens"],
            reference=serializer.validated_data.get("reference", ""),
        )
        return Response(
            LigneReleveBancaireSerializer(ligne).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def pointer(self, request, pk=None):
        releve = self.get_object()
        ligne_id = request.data.get("ligne_id")
        if not ligne_id:
            raise DRFValidationError("ligne_id est obligatoire.")
        RapprochementService.pointer(releve, ligne_id)
        return Response({"status": "pointé"})

    @action(detail=True, methods=["post"])
    def depointer(self, request, pk=None):
        releve = self.get_object()
        ligne_id = request.data.get("ligne_id")
        if not ligne_id:
            raise DRFValidationError("ligne_id est obligatoire.")
        RapprochementService.depointer(releve, ligne_id)
        return Response({"status": "dépointé"})

    @action(detail=True, methods=["post"])
    def valider(self, request, pk=None):
        releve = self.get_object()
        RapprochementService.valider(releve, request.user)
        return Response({"status": "rapproché"})


class ImmobilisationViewSet(EntrepriseScopedViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, AccountingTenantPermission]
    queryset = Immobilisation.objects.prefetch_related("plan_amortissement").all()
    serializer_class = ImmobilisationSerializer
    filterset_fields = ["statut", "type_immobilisation", "entreprise_id"]
    search_fields = ["libelle", "code"]

    @action(detail=True, methods=["post"])
    def calculer_amortissement(self, request, pk=None):
        immobilisation = self.get_object()
        try:
            AmortissementService.generer_plan_amortissement(immobilisation, request.user)
            return Response({"status": "plan généré"})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def comptabiliser_amortissement(self, request, pk=None):
        immobilisation = self.get_object()
        try:
            AmortissementService.comptabiliser_amortissement(immobilisation, request.user)
            return Response({"status": "amortissement comptabilisé"})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)



class DimensionAnalytiqueViewSet(EntrepriseScopedViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, AccountingTenantPermission]
    queryset = DimensionAnalytique.objects.all()
    serializer_class = DimensionAnalytiqueSerializer
    filterset_fields = ["code", "actif"]
    search_fields = ["code", "libelle"]


class ValeurAnalytiqueViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, AccountingTenantPermission]
    serializer_class = ValeurAnalytiqueSerializer
    filterset_fields = ["dimension", "code", "external_id", "actif"]
    search_fields = ["code", "libelle", "external_id"]

    def get_entreprise_id(self):
        return resolve_entreprise_id(self.request)

    def get_queryset(self):
        return ValeurAnalytique.objects.filter(
            dimension__entreprise_id=self.get_entreprise_id()
        ).select_related("dimension")

    def perform_create(self, serializer):
        dimension = serializer.validated_data["dimension"]
        if (dimension.entreprise_id or "") != self.get_entreprise_id():
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Cette dimension analytique appartient à une autre entreprise.")
        serializer.save()


class RegleEvenementComptableViewSet(EntrepriseScopedViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, AccountingTenantPermission]
    queryset = RegleEvenementComptable.objects.all()
    serializer_class = RegleEvenementComptableSerializer
    filterset_fields = ["type_evenement", "code_regle", "actif"]
    search_fields = ["type_evenement", "code_regle"]


class EvenementMetierViewSet(EntrepriseScopedViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, AccountingTenantPermission]
    queryset = EvenementMetier.objects.select_related("ecriture").all()
    serializer_class = EvenementMetierSerializer
    http_method_names = ["get", "post", "head", "options"]
    filterset_fields = ["type_evenement", "source_system", "source_id", "statut"]
    search_fields = ["idempotency_key", "source_id"]

    def get_serializer_class(self):
        if self.action == "create":
            return EvenementIngestSerializer
        return EvenementMetierSerializer

    @action(detail=True, methods=["post"])
    @accounting_storage_operation
    def retry(self, request, pk=None):
        evenement = self.get_object()
        try:
            evenement = EvenementService.retraiter(evenement, user=request.user)
        except AccountingBusy as exc:
            raise AccountingServiceUnavailable(wait=1) from exc
        output = EvenementMetierSerializer(
            evenement, context={"request": request}
        )
        if evenement.statut == "ERREUR":
            return Response(
                output.data,
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        return Response(output.data, status=status.HTTP_200_OK)

    @accounting_storage_operation
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            evenement, created = EvenementService.recevoir(
                entreprise_id=self.get_entreprise_id(),
                type_evenement=data["type_evenement"],
                source_system=data["source_system"],
                source_type=data.get("source_type", ""),
                source_id=data.get("source_id", ""),
                idempotency_key=data["idempotency_key"],
                payload=data.get("payload") or {},
                user=request.user,
            )
        except IdempotencyConflict as exc:
            return Response({"detail": exc.messages[0]}, status=status.HTTP_409_CONFLICT)
        except AccountingBusy as exc:
            raise AccountingServiceUnavailable(wait=1) from exc
        output = EvenementMetierSerializer(evenement, context={"request": request})
        if evenement.statut == "ERREUR":
            return Response(output.data, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        return Response(
            output.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
