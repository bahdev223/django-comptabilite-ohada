from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin

from ..services.bilan_service import BilanService
from ..models import ExerciceComptable
from ..tenant import resolve_entreprise_id


class BilanView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = "comptabilite_ohada/bilan.html"
    permission_required = "comptabilite_ohada.view_ecriturecomptable"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        service = BilanService()
        entreprise_id = resolve_entreprise_id(self.request)
        exercice_id = self.request.GET.get("exercice")
        exercice = ExerciceComptable.objects.filter(
            pk=exercice_id, entreprise_id=entreprise_id
        ).first() if exercice_id else None
        context["bilan"] = service.bilan(
            exercice=exercice, entreprise_id=entreprise_id
        )
        context["resultat"] = service.compte_resultat(
            exercice=exercice, entreprise_id=entreprise_id
        )
        return context


class CompteResultatView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = "comptabilite_ohada/compte_resultat.html"
    permission_required = "comptabilite_ohada.view_ecriturecomptable"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        service = BilanService()
        entreprise_id = resolve_entreprise_id(self.request)
        exercice_id = self.request.GET.get("exercice")
        exercice = ExerciceComptable.objects.filter(
            pk=exercice_id, entreprise_id=entreprise_id
        ).first() if exercice_id else None
        context["resultat"] = service.compte_resultat(
            exercice=exercice, entreprise_id=entreprise_id
        )
        return context
