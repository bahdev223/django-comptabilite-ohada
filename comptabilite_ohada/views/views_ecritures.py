from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.shortcuts import redirect
from django.contrib import messages

from ..models import EcritureComptable
from ..services.ecriture_service import EcritureService


class EcritureListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = EcritureComptable
    template_name = "comptabilite_ohada/ecriture_list.html"
    context_object_name = "ecritures"
    permission_required = "comptabilite_ohada.view_ecriturecomptable"
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset().select_related("journal", "exercice")
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


class EcritureCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = EcritureComptable
    template_name = "comptabilite_ohada/ecriture_form.html"
    fields = ["journal", "exercice", "date_ecriture", "reference", "libelle", "type_operation"]
    permission_required = "comptabilite_ohada.add_ecriturecomptable"

    def form_valid(self, form):
        form.instance.createur = self.request.user
        messages.success(self.request, "Écriture créée avec succès.")
        return super().form_valid(form)


class EcritureUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = EcritureComptable
    template_name = "comptabilite_ohada/ecriture_form.html"
    fields = ["journal", "date_ecriture", "libelle", "type_operation"]
    permission_required = "comptabilite_ohada.change_ecriturecomptable"

    def get_queryset(self):
        return super().get_queryset().filter(validee=False)

    def form_valid(self, form):
        messages.success(self.request, "Écriture modifiée avec succès.")
        return super().form_valid(form)


class EcritureDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = EcritureComptable
    template_name = "comptabilite_ohada/ecriture_confirm_delete.html"
    success_url = reverse_lazy("comptabilite:ecriture_list")
    permission_required = "comptabilite_ohada.delete_ecriturecomptable"

    def get_queryset(self):
        return super().get_queryset().filter(validee=False)

    def delete(self, request, *args, **kwargs):
        messages.success(request, "Écriture supprimée avec succès.")
        return super().delete(request, *args, **kwargs)


class EcritureValiderView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = EcritureComptable
    permission_required = "comptabilite_ohada.change_ecriturecomptable"

    def post(self, request, *args, **kwargs):
        ecriture = self.get_object()
        try:
            EcritureService.valider_ecriture(ecriture, request.user)
            messages.success(request, "Écriture validée avec succès.")
        except Exception as e:
            messages.error(request, str(e))
        return redirect("comptabilite:ecriture_detail", pk=ecriture.pk)
