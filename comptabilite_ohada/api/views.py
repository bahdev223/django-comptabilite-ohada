"""Fail-closed accounting REST API.

Read/query endpoints are tenant-filtered and require model permissions.
Legacy write-capable ModelViewSets have been replaced by read-only views.
Ledger creates/validations/reversals use the audited domain service.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..models import (
    CompteComptable, EcritureComptable, ExerciceComptable,
    JournalComptable, ConfigurationComptable, Immobilisation,
    LigneEcritureComptable,
)
from ..services.ecriture_service import EcritureService
from ..services.exercice_service import ValidationService
from ..services.journal_service import BalanceService, GrandLivreService
from ..services.bilan_service import BilanService
from ..tenancy import resolve_request_tenant, tenant_scope
from .permissions import AccountingModelPermission
from .serializers import (
    CompteComptableSerializer, EcritureComptableSerializer,
    EcritureCreateSerializer, JournalComptableSerializer,
    ExerciceComptableSerializer, ConfigurationComptableSerializer,
    ImmobilisationSerializer,
)


class TenantScopedViewSet:
    """Resolve tenant from a trusted host resolver, not directly from HTTP headers."""

    permission_classes = [IsAuthenticated, AccountingModelPermission]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.tenant_id = resolve_request_tenant(request)
        self._tenant_context = tenant_scope(self.tenant_id)
        self._tenant_context.__enter__()

    def finalize_response(self, request, response, *args, **kwargs):
        try:
            return super().finalize_response(request, response, *args, **kwargs)
        finally:
            context = getattr(self, "_tenant_context", None)
            if context is not None:
                context.__exit__(None, None, None)
                self._tenant_context = None

    def get_queryset(self):
        return super().get_queryset().filter(entreprise_id=self.tenant_id)

    def get_serializer_context(self):
        result = super().get_serializer_context()
        result["tenant_id"] = self.tenant_id
        return result


def _domaine_error(error):
    return ValidationError(getattr(error, "messages", [str(error)]))


class CompteComptableViewSet(TenantScopedViewSet, viewsets.ReadOnlyModelViewSet):
    model = CompteComptable
    queryset = CompteComptable.objects.all()
    serializer_class = CompteComptableSerializer

    @action(detail=True, methods=["get"])
    def solde(self, request, pk=None):
        compte = self.get_object()
        exercice_id = request.query_params.get("exercice")
        qs = LigneEcritureComptable.objects.filter(
            compte=compte,
            ecriture__entreprise_id=self.tenant_id,
            compte__entreprise_id=self.tenant_id,
            ecriture__validee=True,
        )
        if exercice_id:
            exercice = get_object_or_404(
                ExerciceComptable, pk=exercice_id, entreprise_id=self.tenant_id
            )
            qs = qs.filter(ecriture__exercice=exercice)
        aggregates = qs.aggregate(debit=Sum("debit"), credit=Sum("credit"))
        debit = aggregates["debit"] or Decimal("0.00")
        credit = aggregates["credit"] or Decimal("0.00")
        return Response({"solde_debiteur": debit - credit})


class EcritureComptableViewSet(TenantScopedViewSet, viewsets.ReadOnlyModelViewSet):
    model = EcritureComptable
    queryset = EcritureComptable.objects.all()
    serializer_class = EcritureComptableSerializer

    def get_serializer_class(self):
        return EcritureCreateSerializer if self.action == "create" else self.serializer_class

    def create(self, request, *args, **kwargs):
        serializer = EcritureCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        journal = get_object_or_404(
            JournalComptable, pk=data["journal"],
            entreprise_id=self.tenant_id, actif=True,
        )
        exercice = None
        if "exercice" in data:
            exercice = get_object_or_404(
                ExerciceComptable, pk=data["exercice"], entreprise_id=self.tenant_id,
            )
        lines = []
        for line in data["lignes"]:
            account = get_object_or_404(
                CompteComptable, pk=line["compte"], entreprise_id=self.tenant_id,
                actif=True, est_mouvement=True,
            )
            lines.append({
                "compte": account,
                "debit": line["debit"],
                "credit": line["credit"],
                "libelle": line.get("libelle") or data["libelle"],
            })
        try:
            entry = EcritureService.creer_ecriture(
                reference=data["reference"],
                date_ecriture=data["date_ecriture"],
                libelle=data["libelle"],
                journal=journal,
                exercice=exercice,
                piece=data.get("piece"),
                lignes=lines,
                validee=False,
                user=request.user,
                entreprise_id=self.tenant_id,
            )
        except DjangoValidationError as exc:
            raise _domaine_error(exc) from exc
        return Response(
            EcritureComptableSerializer(entry, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def valider(self, request, pk=None):
        entry = self.get_object()
        try:
            entry = ValidationService.valider_ecriture(
                entry, user=request.user, entreprise_id=self.tenant_id
            )
        except DjangoValidationError as exc:
            raise _domaine_error(exc) from exc
        return Response({"id": entry.pk, "status": "validee"})

    @action(detail=True, methods=["post"])
    def annuler(self, request, pk=None):
        entry = self.get_object()
        reason = request.data.get("raison", "")
        if not isinstance(reason, str) or len(reason) > 200:
            raise ValidationError({"raison": "Motif invalide."})
        try:
            reversal = ValidationService.annuler_ecriture(
                entry, user=request.user, raison=reason, entreprise_id=self.tenant_id
            )
        except DjangoValidationError as exc:
            raise _domaine_error(exc) from exc
        return Response({"id": reversal.pk, "status": "contrepassation_creee"})

    def _exercice(self, request):
        exercice_id = request.query_params.get("exercice")
        if exercice_id:
            return get_object_or_404(
                ExerciceComptable, pk=exercice_id, entreprise_id=self.tenant_id,
            )
        return None

    @action(detail=False, methods=["get"])
    def balance(self, request):
        data = BalanceService.balance(exercice=self._exercice(request))
        return Response([
            {
                "compte": {"id": row["compte"].pk, "code": row["compte"].code, "libelle": row["compte"].libelle},
                "total_debit": row["total_debit"],
                "total_credit": row["total_credit"],
                "solde": row["solde"],
            }
            for row in data
        ])

    @action(detail=False, methods=["get"])
    def grand_livre(self, request):
        data = GrandLivreService.grand_livre(
            compte_code=request.query_params.get("compte"),
            exercice=self._exercice(request),
        )
        return Response([
            {
                **{k: v for k, v in row.items() if k != "compte"},
                "compte": {"id": row["compte"].pk, "code": row["compte"].code},
            }
            for row in data
        ])

    @action(detail=False, methods=["get"])
    def bilan(self, request):
        return Response(BilanService.bilan(exercice=self._exercice(request)))

    @action(detail=False, methods=["get"])
    def compte_resultat(self, request):
        return Response(BilanService.compte_resultat(exercice=self._exercice(request)))


class JournalComptableViewSet(TenantScopedViewSet, viewsets.ReadOnlyModelViewSet):
    model = JournalComptable
    queryset = JournalComptable.objects.all()
    serializer_class = JournalComptableSerializer

    @action(detail=True, methods=["get"])
    def ecritures(self, request, pk=None):
        journal = self.get_object()
        qs = EcritureComptable.objects.filter(
            journal=journal, entreprise_id=self.tenant_id
        ).order_by("-date_ecriture", "-pk")
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(
                EcritureComptableSerializer(
                    page, many=True, context=self.get_serializer_context()
                ).data
            )
        return Response(
            EcritureComptableSerializer(
                qs, many=True, context=self.get_serializer_context()
            ).data
        )


class ExerciceComptableViewSet(TenantScopedViewSet, viewsets.ReadOnlyModelViewSet):
    model = ExerciceComptable
    queryset = ExerciceComptable.objects.all()
    serializer_class = ExerciceComptableSerializer


class ConfigurationComptableViewSet(TenantScopedViewSet, viewsets.ReadOnlyModelViewSet):
    model = ConfigurationComptable
    queryset = ConfigurationComptable.objects.all()
    serializer_class = ConfigurationComptableSerializer


class ImmobilisationViewSet(TenantScopedViewSet, viewsets.ReadOnlyModelViewSet):
    model = Immobilisation
    queryset = Immobilisation.objects.all()
    serializer_class = ImmobilisationSerializer
