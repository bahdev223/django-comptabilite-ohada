# django-comptabilite-ohada

Paquet Django pour la comptabilité OHADA/SYSCOHADA en partie double.

## Fonctionnalités

- Plan comptable SYSCOHADA (classes 1 à 8)
- Écritures comptables en partie double avec validation
- Journaux auxiliaires (Ventes, Achats, Trésorerie, Banque, Caisse, OD, etc.)
- Balance générale, Grand livre
- Bilan et Compte de résultat
- Gestion des exercices comptables (ouverture, clôture, réouverture)
- Immobilisations et amortissements (linéaire, dégressif)
- Rapprochement bancaire
- Multi-société
- Export CSV
- API REST complète (DRF)
- Intégration signal-based avec django-comptes
- Moteur de règles comptables

## Installation

```bash
pip install django-comptabilite-ohada
```

Ou depuis GitHub :
```bash
pip install git+https://github.com/bahdev223/django-comptabilite-ohada.git
```

## Configuration

```python
# settings.py
INSTALLED_APPS = [
    ...
    'comptabilite_ohada',
]

COMPTABILITE_OHADA = {
    'API_ENABLED': True,
    'COMPTES_INTEGRATION_ENABLED': True,
    'DEVISE_PAR_DEFAUT': 'XAF',
    'AUTO_CREATE_JOURNAUX': True,
    'AUTO_CREATE_EXERCICE': True,
}
```

### Migrations

```bash
python manage.py migrate comptabilite_ohada
```

### Charger le plan comptable SYSCOHADA

```bash
python manage.py charger_plan_comptable
```

## Utilisation

### URLs

```python
from django.urls import include, path

urlpatterns = [
    path('comptabilite/', include('comptabilite_ohada.urls')),
]
```

### API REST

- `GET /api/comptabilite/comptes/` — Liste des comptes
- `POST /api/comptabilite/ecritures/` — Créer une écriture
- `GET /api/comptabilite/ecritures/balance/` — Balance
- `GET /api/comptabilite/ecritures/grand_livre/` — Grand livre
- `GET /api/comptabilite/ecritures/bilan/` — Bilan
- `GET /api/comptabilite/ecritures/compte_resultat/` — Compte de résultat
- `POST /api/comptabilite/ecritures/<id>/valider/` — Valider une écriture
- `POST /api/comptabilite/exercices/<id>/cloturer/` — Clôturer un exercice

## Intégration avec django-comptes

Quand un mouvement est créé dans django-comptes, `django-comptabilite-ohada` crée automatiquement les écritures comptables correspondantes via les signaux Django.

Activation dans les settings :
```python
COMPTABILITE_OHADA = {
    'COMPTES_INTEGRATION_ENABLED': True,
}
```

## Licence

MIT
