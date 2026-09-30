from django.views.generic import ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin

from ..models import ReleveBancaire
from ..tenant import resolve_entreprise_id


class RapprochementListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = ReleveBancaire
    template_name = "comptabilite_ohada/rapprochement_list.html"
    context_object_name = "releves"
    permission_required = "comptabilite_ohada.view_relevebancaire"

    def get_queryset(self):
        entreprise_id = resolve_entreprise_id(self.request)
        return super().get_queryset().filter(entreprise_id=entreprise_id)


class RapprochementDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = ReleveBancaire
    template_name = "comptabilite_ohada/rapprochement_detail.html"
    context_object_name = "releve"
    permission_required = "comptabilite_ohada.view_relevebancaire"

    def get_queryset(self):
        entreprise_id = resolve_entreprise_id(self.request)
        return super().get_queryset().filter(entreprise_id=entreprise_id)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["lignes"] = self.object.lignes.all()
        return context
