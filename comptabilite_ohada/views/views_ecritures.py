from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db import transaction
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from ..forms import EcritureComptableForm, LigneEcritureFormSet
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
        statut = self.request.GET.get("status")
        if statut == "validee":
            qs = qs.filter(validee=True)
        elif statut == "non_validee":
            qs = qs.filter(validee=False)
        return qs.order_by("-date_ecriture", "-created_at")


class EcritureDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = EcritureComptable
    template_name = "comptabilite_ohada/ecriture_detail.html"
    context_object_name = "ecriture"
    permission_required = "comptabilite_ohada.view_ecriturecomptable"

    def get_queryset(self):
        return super().get_queryset().filter(
            entreprise_id=_entreprise_id(self.request)
        ).select_related("journal", "exercice").prefetch_related(
            "lignes__compte",
            "lignes__affectations_analytiques__dimension",
            "lignes__affectations_analytiques__valeur",
        )


class EcritureFormMixin:
    form_class = EcritureComptableForm
    template_name = "comptabilite_ohada/ecriture_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["entreprise_id"] = _entreprise_id(self.request)
        return kwargs

    def get_formset(self, instance=None):
        return LigneEcritureFormSet(
            data=self.request.POST or None,
            instance=instance,
            prefix="lignes",
            form_kwargs={"entreprise_id": _entreprise_id(self.request)},
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if "formset" not in context:
            context["formset"] = self.get_formset(
                instance=getattr(self, "object", None)
            )
        return context

    def _save_with_lines(self, form, formset):
        entreprise_id = _entreprise_id(self.request)
        with transaction.atomic():
            self.object = form.save(commit=False)
            self.object.entreprise_id = entreprise_id
            if not self.object.created_by:
                self.object.created_by = self.request.user.get_username()
            self.object.validee = False
            self.object.save()

            formset.instance = self.object
            formset.save()

        messages.success(
            self.request,
            "Écriture enregistrée en brouillon. Validez-la après contrôle.",
        )
        return redirect(
            "comptabilite:ecriture_detail",
            pk=self.object.pk,
        )


class EcritureCreateView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    EcritureFormMixin,
    CreateView,
):
    model = EcritureComptable
    permission_required = "comptabilite_ohada.add_ecriturecomptable"

    def form_valid(self, form):
        formset = self.get_formset()
        if not formset.is_valid():
            return self.render_to_response(
                self.get_context_data(form=form, formset=formset)
            )
        return self._save_with_lines(form, formset)


class EcritureUpdateView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    EcritureFormMixin,
    UpdateView,
):
    model = EcritureComptable
    permission_required = "comptabilite_ohada.change_ecriturecomptable"

    def get_queryset(self):
        return super().get_queryset().filter(
            validee=False,
            entreprise_id=_entreprise_id(self.request),
        )

    def form_valid(self, form):
        formset = self.get_formset(instance=self.object)
        if not formset.is_valid():
            return self.render_to_response(
                self.get_context_data(form=form, formset=formset)
            )
        return self._save_with_lines(form, formset)


class EcritureDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = EcritureComptable
    template_name = "comptabilite_ohada/ecriture_confirm_delete.html"
    success_url = reverse_lazy("comptabilite:ecriture_list")
    permission_required = "comptabilite_ohada.delete_ecriturecomptable"

    def get_queryset(self):
        return super().get_queryset().filter(
            validee=False,
            entreprise_id=_entreprise_id(self.request),
        )

    def delete(self, request, *args, **kwargs):
        messages.success(request, "Écriture brouillon supprimée.")
        return super().delete(request, *args, **kwargs)


class EcritureValiderView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = EcritureComptable
    permission_required = "comptabilite_ohada.change_ecriturecomptable"

    def get_queryset(self):
        return super().get_queryset().filter(
            entreprise_id=_entreprise_id(self.request)
        )

    def post(self, request, *args, **kwargs):
        ecriture = self.get_object()
        try:
            ValidationService.valider_ecriture(ecriture, request.user)
            messages.success(request, "Écriture validée avec succès.")
        except Exception as exc:
            messages.error(request, str(exc))
        return redirect("comptabilite:ecriture_detail", pk=ecriture.pk)
