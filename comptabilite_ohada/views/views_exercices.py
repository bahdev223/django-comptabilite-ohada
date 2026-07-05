from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.shortcuts import redirect

from ..models import ExerciceComptable
from ..services.exercice_service import ExerciceService


class ExerciceListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = ExerciceComptable
    template_name = "comptabilite_ohada/exercice_list.html"
    context_object_name = "exercices"
    permission_required = "comptabilite_ohada.view_exercicecomptable"


class ExerciceDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = ExerciceComptable
    template_name = "comptabilite_ohada/exercice_detail.html"
    context_object_name = "exercice"
    permission_required = "comptabilite_ohada.view_exercicecomptable"


class ExerciceCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = ExerciceComptable
    template_name = "comptabilite_ohada/exercice_form.html"
    fields = ["code", "libelle", "date_debut", "date_fin", "societe"]
    permission_required = "comptabilite_ohada.add_exercicecomptable"

    def form_valid(self, form):
        messages.success(self.request, "Exercice créé avec succès.")
        return super().form_valid(form)


class ExerciceCloturerView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = ExerciceComptable
    permission_required = "comptabilite_ohada.change_exercicecomptable"

    def post(self, request, *args, **kwargs):
        exercice = self.get_object()
        try:
            ExerciceService.cloturer(exercice, request.user)
            messages.success(request, "Exercice clôturé avec succès.")
        except Exception as e:
            messages.error(request, str(e))
        return redirect("comptabilite:exercice_detail", pk=exercice.pk)


class ExerciceRouvrirView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = ExerciceComptable
    permission_required = "comptabilite_ohada.change_exercicecomptable"

    def post(self, request, *args, **kwargs):
        exercice = self.get_object()
        try:
            ExerciceService.rouvrir(exercice)
            messages.success(request, "Exercice rouvert avec succès.")
        except Exception as e:
            messages.error(request, str(e))
        return redirect("comptabilite:exercice_detail", pk=exercice.pk)
