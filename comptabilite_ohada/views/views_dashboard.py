from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin

from ..services.dashboard_service import DashboardService


class DashboardView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = "comptabilite_ohada/dashboard.html"
    permission_required = "comptabilite_ohada.view_ecriturecomptable"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        service = DashboardService()
        entreprise_id = str(getattr(self.request.user, "entreprise_id", "") or "")
        context["total_ecritures"] = service.compter_ecritures(entreprise_id)
        context["ecritures_non_validees"] = service.compter_ecritures_non_validees(entreprise_id)
        context["dernieres_ecritures"] = service.dernieres_ecritures(entreprise_id=entreprise_id)
        context["exercice_courant"] = service.exercice_courant(entreprise_id)
        context["totaux_par_journal"] = service.totaux_par_journal(entreprise_id)
        return context
