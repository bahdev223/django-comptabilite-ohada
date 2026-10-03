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

## Intégration analytique avec SahelTech Platform

Pour exposer le service comptable à la plateforme, monter exclusivement
`comptabilite_ohada.integration_urls` comme `ROOT_URLCONF` sur un hôte dédié.
L'ancienne API REST de `comptabilite_ohada.urls` ne doit pas être montée sur cet
hôte : elle n'utilise pas les clés d'intégration par entreprise.

```python
import os

ROOT_URLCONF = 'comptabilite_ohada.integration_urls'
COMPTABILITE_OHADA = {
    'COMPTES_INTEGRATION_ENABLED': False,
    'DEVISE_PAR_DEFAUT': 'XOF',
    'INTEGRATION_KEYS': {
        'CODE_ENTREPRISE': os.environ['ACCOUNTING_KEY_CODE_ENTREPRISE'],
    },
}
```

L'hôte expose `POST /api/v1/events/` et `GET /api/v1/analytics/costs/`.
Chaque requête porte `X-API-Key`; la clé détermine l'entreprise côté serveur.
`PROJECT` est obligatoire pour la recherche de coûts et les filtres
`PHASE`, `ACTIVITY`, `TASK`, `MISSION`, `CONTRACT` sont facultatifs. Les écritures
reçues sont équilibrées, enregistrées une seule fois par clé d'idempotence et
rattachées à des comptes, journaux et exercices de cette entreprise. Les coûts
proviennent seulement des lignes de charges validées. Configurer la même devise
dans la plateforme et dans le service comptable.

## Licence

MIT
