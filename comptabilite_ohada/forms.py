from django import forms
from django.forms import inlineformset_factory

from .models import (
    CompteComptable,
    EcritureComptable,
    ExerciceComptable,
    JournalComptable,
    LigneEcritureComptable,
)


class EcritureComptableForm(forms.ModelForm):
    class Meta:
        model = EcritureComptable
        fields = [
            "journal",
            "exercice",
            "date_ecriture",
            "reference",
            "libelle",
            "piece",
        ]
        widgets = {
            "date_ecriture": forms.DateInput(attrs={"type": "date"}),
            "libelle": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, entreprise_id="", **kwargs):
        super().__init__(*args, **kwargs)
        self.entreprise_id = entreprise_id or ""
        self.fields["journal"].queryset = JournalComptable.objects.filter(
            entreprise_id=self.entreprise_id,
            actif=True,
        ).order_by("code")
        self.fields["exercice"].queryset = ExerciceComptable.objects.filter(
            entreprise_id=self.entreprise_id,
            cloture=False,
        ).order_by("-date_debut")

    def clean_reference(self):
        reference = self.cleaned_data["reference"]
        qs = EcritureComptable.objects.filter(
            entreprise_id=self.entreprise_id,
            reference=reference,
        )
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(
                "Cette référence existe déjà pour cette entreprise."
            )
        return reference

    def clean(self):
        cleaned = super().clean()
        exercice = cleaned.get("exercice")
        date_ecriture = cleaned.get("date_ecriture")
        if exercice and date_ecriture:
            if exercice.cloture:
                self.add_error("exercice", "Cet exercice est clôturé.")
            elif not (
                exercice.date_debut <= date_ecriture <= exercice.date_fin
            ):
                self.add_error(
                    "date_ecriture",
                    "La date est hors de la période de l'exercice.",
                )
        return cleaned


class LigneEcritureComptableForm(forms.ModelForm):
    class Meta:
        model = LigneEcritureComptable
        fields = ["compte", "libelle", "debit", "credit"]

    def __init__(self, *args, entreprise_id="", **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["compte"].queryset = CompteComptable.objects.filter(
            entreprise_id=entreprise_id or "",
            actif=True,
            est_mouvement=True,
        ).order_by("code")


LigneEcritureFormSet = inlineformset_factory(
    EcritureComptable,
    LigneEcritureComptable,
    form=LigneEcritureComptableForm,
    fields=["compte", "libelle", "debit", "credit"],
    extra=2,
    min_num=2,
    validate_min=True,
    can_delete=True,
)
