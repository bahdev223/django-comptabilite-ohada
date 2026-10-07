from django.views.generic import ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin

from ..models import Immobilisation
from ..tenant import resolve_entreprise_id


class ImmobilisationListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Immobilisation
    template_name = "comptabilite_ohada/immobilisation_list.html"
    context_object_name = "immobilisations"
    permission_required = "comptabilite_ohada.view_immobilisation"

    def get_queryset(self):
        entreprise_id = resolve_entreprise_id(self.request)
        return super().get_queryset().filter(entreprise_id=entreprise_id)


class ImmobilisationDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = Immobilisation
    template_name = "comptabilite_ohada/immobilisation_detail.html"
    context_object_name = "immobilisation"
    permission_required = "comptabilite_ohada.view_immobilisation"

    def get_queryset(self):
        entreprise_id = resolve_entreprise_id(self.request)
        return super().get_queryset().filter(entreprise_id=entreprise_id)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["plan"] = self.object.plan_amortissement.all()
        return context
