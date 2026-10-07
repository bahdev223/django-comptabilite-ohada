from django.http import HttpResponse
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.views import View
from ..services.export_service import ExportService
from ..tenant import resolve_entreprise_id


class ExportCSVView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "comptabilite_ohada.view_ecriturecomptable"

    def get(self, request, *args, **kwargs):
        export_type = request.GET.get("type", "ecritures")
        exercice_id = request.GET.get("exercice")
        service = ExportService()

        from ..models import ExerciceComptable
        entreprise_id = resolve_entreprise_id(request)
        exercice = ExerciceComptable.objects.filter(
            pk=exercice_id, entreprise_id=entreprise_id
        ).first() if exercice_id else None

        if export_type == "balance":
            content = service.export_balance_csv(
                exercice=exercice, entreprise_id=entreprise_id
            )
            filename = "balance.csv"
        elif export_type == "grand_livre":
            content = service.export_grand_livre_csv(
                exercice=exercice, entreprise_id=entreprise_id
            )
            filename = "grand_livre.csv"
        else:
            content = service.export_ecritures_csv(
                exercice=exercice, entreprise_id=entreprise_id
            )
            filename = "ecritures.csv"

        return content
