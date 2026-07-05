from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin

from ..services.bilan_service import BilanService


class BilanView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = "comptabilite_ohada/bilan.html"
    permission_required = "comptabilite_ohada.view_ecriturecomptable"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        service = BilanService()
        exercice_id = self.request.GET.get("exercice")
        context["bilan"] = service.generer_bilan(exercice_id=exercice_id)
        context["resultat"] = service.generer_compte_resultat(exercice_id=exercice_id)
        return context


class CompteResultatView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = "comptabilite_ohada/compte_resultat.html"
    permission_required = "comptabilite_ohada.view_ecriturecomptable"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        service = BilanService()
        exercice_id = self.request.GET.get("exercice")
        context["resultat"] = service.generer_compte_resultat(exercice_id=exercice_id)
        return context
