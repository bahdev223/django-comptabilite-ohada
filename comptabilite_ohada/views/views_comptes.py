from django.views.generic import ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin

from ..models import CompteComptable
from ..services.journal_service import BalanceService
from ..tenant import resolve_entreprise_id


class CompteComptableListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = CompteComptable
    template_name = "comptabilite_ohada/compte_list.html"
    context_object_name = "comptes"
    permission_required = "comptabilite_ohada.view_comptecomptable"

    def get_queryset(self):
        qs = super().get_queryset().filter(
            entreprise_id=resolve_entreprise_id(self.request)
        )
        classe = self.request.GET.get("classe")
        if classe:
            qs = qs.filter(code__startswith=str(classe))
        actif = self.request.GET.get("actif")
        if actif is not None:
            qs = qs.filter(actif=(actif == "1"))
        return qs.order_by("code")


class CompteComptableDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = CompteComptable
    template_name = "comptabilite_ohada/compte_detail.html"
    context_object_name = "compte"
    permission_required = "comptabilite_ohada.view_comptecomptable"

    def get_queryset(self):
        return super().get_queryset().filter(
            entreprise_id=resolve_entreprise_id(self.request)
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["solde"] = BalanceService.solde_compte(self.object)
        return context
