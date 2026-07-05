from django import template

register = template.Library()


@register.filter
def somme_debit(lignes):
    return sum(l.debit for l in lignes)


@register.filter
def somme_credit(lignes):
    return sum(l.credit for l in lignes)


@register.filter
def cls(value):
    if value >= 0:
        return "text-success"
    return "text-danger"


@register.simple_tag
def total_lignes(ecriture):
    return sum(l.debit for l in ecriture.lignes.all())


@register.filter
def classe_nom(classe):
    noms = {
        "1": "Comptes de ressources durables",
        "2": "Comptes d'actif immobilisé",
        "3": "Comptes de stocks",
        "4": "Comptes de tiers",
        "5": "Comptes de trésorerie",
        "6": "Comptes de charges",
        "7": "Comptes de produits",
        "8": "Comptes des engagements hors bilan",
    }
    return noms.get(str(classe), f"Classe {classe}")


@register.simple_tag
def statut_badge(validee):
    if validee:
        return '<span class="badge bg-success">Validée</span>'
    return '<span class="badge bg-warning">En attente</span>'
