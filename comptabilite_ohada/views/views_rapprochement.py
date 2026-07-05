from django.views.generic import ListView, DetailView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin

from ..models import ReleveBancaire


class RapprochementListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = ReleveBancaire
    template_name = "comptabilite_ohada/rapprochement_list.html"
    context_object_name = "releves"
    permission_required = "comptabilite_ohada.view_relevebancaire"


class RapprochementDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = ReleveBancaire
    template_name = "comptabilite_ohada/rapprochement_detail.html"
    context_object_name = "releve"
    permission_required = "comptabilite_ohada.view_relevebancaire"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["lignes"] = self.object.lignes.select_related("ecriture").all()
        return context
