from django.views.generic import ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin

from ..models import JournalComptable
from ..services.journal_service import BalanceService, GrandLivreService


class JournalListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = JournalComptable
    template_name = "comptabilite_ohada/journal_list.html"
    context_object_name = "journaux"
    permission_required = "comptabilite_ohada.view_journalcomptable"


class JournalDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = JournalComptable
    template_name = "comptabilite_ohada/journal_detail.html"
    context_object_name = "journal"
    permission_required = "comptabilite_ohada.view_journalcomptable"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["ecritures"] = self.object.ecritures.select_related("exercice").order_by("-date_ecriture")[:50]
        return context


class BalanceView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    template_name = "comptabilite_ohada/balance.html"
    permission_required = "comptabilite_ohada.view_ecriturecomptable"

    def get_queryset(self):
        return []

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        service = BalanceService()
        exercice_id = self.request.GET.get("exercice")
        from ..models import ExerciceComptable
        exercice = ExerciceComptable.objects.filter(pk=exercice_id).first() if exercice_id else None
        context["balance"] = service.balance(exercice=exercice)
        context["total_debit"] = sum(l["total_debit"] for l in context["balance"])
        context["total_credit"] = sum(l["total_credit"] for l in context["balance"])
        return context


class GrandLivreView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    template_name = "comptabilite_ohada/grand_livre.html"
    permission_required = "comptabilite_ohada.view_ecriturecomptable"

    def get_queryset(self):
        return []

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        service = GrandLivreService()
        compte_code = self.request.GET.get("compte")
        exercice_id = self.request.GET.get("exercice")
        from ..models import ExerciceComptable
        exercice = ExerciceComptable.objects.filter(pk=exercice_id).first() if exercice_id else None
        context["lignes"] = service.grand_livre(compte_code=compte_code, exercice=exercice)
        return context
