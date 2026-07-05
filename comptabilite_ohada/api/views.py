from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters import rest_framework as filters
from django.db.models import Sum, Q
from django.utils import timezone

from ..models import (
    CompteComptable, EcritureComptable, LigneEcritureComptable,
    JournalComptable, ExerciceComptable, ConfigurationComptable,
    Immobilisation, PlanAmortissement,
)
from ..services.ecriture_service import EcritureService
from ..services.journal_service import BalanceService, GrandLivreService
from ..services.bilan_service import BilanService
from ..services.exercice_service import ExerciceService
from ..services.amortissement_service import AmortissementService
from .serializers import (
    CompteComptableSerializer, EcritureComptableSerializer,
    EcritureCreateSerializer, JournalComptableSerializer,
    ExerciceComptableSerializer, ConfigurationComptableSerializer,
    ImmobilisationSerializer, PlanAmortissementSerializer,
)


class CompteComptableViewSet(viewsets.ModelViewSet):
    queryset = CompteComptable.objects.all()
    serializer_class = CompteComptableSerializer
    filterset_fields = ["code", "classe", "nature", "type_compte", "actif"]
    search_fields = ["code", "libelle"]

    @action(detail=True, methods=["get"])
    def solde(self, request, pk=None):
        compte = self.get_object()
        exercice_id = request.query_params.get("exercice")
        qs = LigneEcritureComptable.objects.filter(
            compte=compte, ecriture__validee=True,
        )
        total_debit = qs.aggregate(total=Sum("debit"))["total"] or 0
        total_credit = qs.aggregate(total=Sum("credit"))["total"] or 0
        return Response({"solde": float(total_debit) - float(total_credit)})


class EcritureComptableViewSet(viewsets.ModelViewSet):
    queryset = EcritureComptable.objects.prefetch_related("lignes__compte").all()
    filterset_fields = ["validee", "journal", "exercice", "type_operation"]
    search_fields = ["reference", "libelle"]

    def get_serializer_class(self):
        if self.action == "create":
            return EcritureCreateSerializer
        return EcritureComptableSerializer

    @action(detail=True, methods=["post"])
    def valider(self, request, pk=None):
        ecriture = self.get_object()
        if ecriture.validee:
            return Response({"error": "Déjà validée"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            EcritureService.valider_ecriture(ecriture, request.user)
            return Response({"status": "validée"})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def annuler(self, request, pk=None):
        ecriture = self.get_object()
        try:
            EcritureService.annuler_ecriture(ecriture, request.user)
            return Response({"status": "annulée"})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["get"])
    def balance(self, request):
        exercice_id = request.query_params.get("exercice")
        service = BalanceService()
        exercice = ExerciceComptable.objects.filter(pk=exercice_id).first() if exercice_id else None
        data = service.balance(exercice=exercice)
        return Response(data)

    @action(detail=False, methods=["get"])
    def grand_livre(self, request):
        compte_code = request.query_params.get("compte")
        exercice_id = request.query_params.get("exercice")
        service = GrandLivreService()
        exercice = ExerciceComptable.objects.filter(pk=exercice_id).first() if exercice_id else None
        data = service.grand_livre(compte_code=compte_code, exercice=exercice)
        return Response(data)

    @action(detail=False, methods=["get"])
    def bilan(self, request):
        exercice_id = request.query_params.get("exercice")
        service = BilanService()
        exercice = ExerciceComptable.objects.filter(pk=exercice_id).first() if exercice_id else None
        bilan = service.bilan(exercice=exercice)
        return Response(bilan)

    @action(detail=False, methods=["get"])
    def compte_resultat(self, request):
        exercice_id = request.query_params.get("exercice")
        service = BilanService()
        exercice = ExerciceComptable.objects.filter(pk=exercice_id).first() if exercice_id else None
        resultat = service.compte_resultat(exercice=exercice)
        return Response(resultat)


class JournalComptableViewSet(viewsets.ModelViewSet):
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


class ExerciceComptableViewSet(viewsets.ModelViewSet):
    queryset = ExerciceComptable.objects.all()
    serializer_class = ExerciceComptableSerializer
    filterset_fields = ["cloture", "societe"]
    search_fields = ["code", "libelle"]

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
            ExerciceService.rouvrir(exercice)
            return Response({"status": "rouvert"})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ConfigurationComptableViewSet(viewsets.ModelViewSet):
    queryset = ConfigurationComptable.objects.all()
    serializer_class = ConfigurationComptableSerializer


class ImmobilisationViewSet(viewsets.ModelViewSet):
    queryset = Immobilisation.objects.prefetch_related("plan_amortissement").all()
    serializer_class = ImmobilisationSerializer
    filterset_fields = ["statut", "mode_amortissement", "societe"]
    search_fields = ["designation", "code"]

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
