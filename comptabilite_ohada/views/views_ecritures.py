from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.shortcuts import redirect
from django.contrib import messages

from ..models import EcritureComptable
from ..services.exercice_service import ValidationService
from ..tenant import resolve_entreprise_id


def _entreprise_id(request):
    return resolve_entreprise_id(request)


class EcritureListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = EcritureComptable
    template_name = "comptabilite_ohada/ecriture_list.html"
    context_object_name = "ecritures"
    permission_required = "comptabilite_ohada.view_ecriturecomptable"
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset().filter(
            entreprise_id=_entreprise_id(self.request)
        ).select_related("journal", "exercice")
        qs = qs.prefetch_related("lignes__compte")
        status = self.request.GET.get("status")
        if status == "validee":
            qs = qs.filter(validee=True)
        elif status == "non_validee":
            qs = qs.filter(validee=False)
        return qs.order_by("-date_ecriture", "-created_at")


class EcritureDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = EcritureComptable
    template_name = "comptabilite_ohada/ecriture_detail.html"
    context_object_name = "ecriture"
    permission_required = "comptabilite_ohada.view_ecriturecomptable"

    def get_queryset(self):
        return super().get_queryset().filter(entreprise_id=_entreprise_id(self.request))


class EcritureCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = EcritureComptable
    template_name = "comptabilite_ohada/ecriture_form.html"
    fields = ["journal", "exercice", "date_ecriture", "reference", "libelle", "piece"]
    permission_required = "comptabilite_ohada.add_ecriturecomptable"

    def form_valid(self, form):
        entreprise_id = _entreprise_id(self.request)
        if (form.cleaned_data["journal"].entreprise_id or "") != entreprise_id:
            form.add_error("journal", "Ce journal appartient à une autre entreprise.")
            return self.form_invalid(form)
        exercice = form.cleaned_data["exercice"]
        if (exercice.entreprise_id or "") != entreprise_id:
            form.add_error("exercice", "Cet exercice appartient à une autre entreprise.")
            return self.form_invalid(form)
        if exercice.cloture:
            form.add_error("exercice", "Cet exercice est clôturé.")
            return self.form_invalid(form)
        date_ecriture = form.cleaned_data["date_ecriture"]
        if not (exercice.date_debut <= date_ecriture <= exercice.date_fin):
            form.add_error("date_ecriture", "La date est hors de la période de l'exercice.")
            return self.form_invalid(form)
        form.instance.created_by = self.request.user.get_username()
        form.instance.entreprise_id = entreprise_id
        messages.success(self.request, "Écriture créée avec succès.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("comptabilite:ecriture_detail", kwargs={"pk": self.object.pk})


class EcritureUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = EcritureComptable
    template_name = "comptabilite_ohada/ecriture_form.html"
    fields = ["journal", "date_ecriture", "libelle", "piece"]
    permission_required = "comptabilite_ohada.change_ecriturecomptable"

    def get_queryset(self):
        return super().get_queryset().filter(
            validee=False, entreprise_id=_entreprise_id(self.request)
        )

    def form_valid(self, form):
        messages.success(self.request, "Écriture modifiée avec succès.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("comptabilite:ecriture_detail", kwargs={"pk": self.object.pk})


class EcritureDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = EcritureComptable
    template_name = "comptabilite_ohada/ecriture_confirm_delete.html"
    success_url = reverse_lazy("comptabilite:ecriture_list")
    permission_required = "comptabilite_ohada.delete_ecriturecomptable"

    def get_queryset(self):
        return super().get_queryset().filter(
            validee=False, entreprise_id=_entreprise_id(self.request)
        )

    def delete(self, request, *args, **kwargs):
        messages.success(request, "Écriture supprimée avec succès.")
        return super().delete(request, *args, **kwargs)


class EcritureValiderView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = EcritureComptable
    permission_required = "comptabilite_ohada.change_ecriturecomptable"

    def get_queryset(self):
        return super().get_queryset().filter(entreprise_id=_entreprise_id(self.request))

    def post(self, request, *args, **kwargs):
        ecriture = self.get_object()
        try:
            ValidationService.valider_ecriture(ecriture, request.user)
            messages.success(request, "Écriture validée avec succès.")
        except Exception as e:
            messages.error(request, str(e))
        return redirect("comptabilite:ecriture_detail", pk=ecriture.pk)
