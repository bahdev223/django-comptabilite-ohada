# django-comptabilite-ohada

Moteur comptable Django autonome et intégrable pour la comptabilité OHADA/SYSCOHADA en partie double.

Le dépôt peut être utilisé de deux façons :

1. comme **app Django réutilisable** dans un ERP existant ;
2. comme **service comptable autonome** exposé par API via le projet `standalone`.

## Principes d'architecture

Le moteur comptable reste volontairement abstrait :

```text
Le métier connaît la comptabilité.
La comptabilité ne connaît jamais le métier.
```

Il ne contient aucune dépendance directe vers des modèles Projet, Chantier, Mission, Installation, BTP, Solar, etc.

Les applications externes communiquent via :

- API REST versionnée ;
- événements métier ;
- références externes ;
- clés d'idempotence ;
- dimensions analytiques génériques.

## Fonctionnalités

- plan comptable SYSCOHADA, y compris catégorie analytique ;
- écritures en partie double ;
- contrôle strict débit = crédit ;
- journaux comptables ;
- exercices comptables et clôture ;
- balance générale ;
- grand livre ;
- compte de résultat ;
- bilan de synthèse ;
- immobilisations et amortissements ;
- rapprochement bancaire ;
- multi-entreprise ;
- traçabilité des systèmes externes ;
- idempotence des intégrations ;
- contre-passation des écritures ;
- comptabilité analytique générique ;
- inbox d'événements métier ;
- mapping événement -> règle comptable ;
- API REST DRF ;
- intégration optionnelle avec `django-comptes` ;
- mode de déploiement autonome ;
- Dockerfile ;
- CI GitHub Actions.

## Installation comme package

```bash
pip install git+https://github.com/bahdev223/django-comptabilite-ohada.git
```

Ou avec l'API REST :

```bash
pip install "django-comptabilite-ohada[rest]"
```

Dans `settings.py` :

```python
INSTALLED_APPS = [
    # ...
    "comptabilite_ohada",
]

COMPTABILITE_OHADA = {
    "API_ENABLED": True,
    "COMPTES_INTEGRATION_ENABLED": False,
}
```

Puis :

```bash
python manage.py migrate comptabilite_ohada
python manage.py charger_plan_comptable
```

## Déploiement autonome

Le dépôt contient un projet Django minimal dans `standalone/`.

```bash
pip install -e ".[rest]"
python manage.py migrate
python manage.py charger_plan_comptable
python manage.py runserver
```

Ou avec Docker :

```bash
docker build -t django-comptabilite-ohada .
docker run -p 8000:8000 \
  -e DJANGO_SECRET_KEY="change-me" \
  django-comptabilite-ohada
```

## API cible

Le contrat stable cible est :

```text
/api/v1/
```

Principales ressources :

```text
GET      /api/v1/health/
POST     /api/v1/auth/token/
GET      /api/v1/organisations/
GET/POST /api/v1/comptes/
GET/POST /api/v1/journaux/
GET/POST /api/v1/exercices/
GET/POST /api/v1/ecritures/

GET      /api/v1/ecritures/balance/
GET      /api/v1/ecritures/grand_livre/
GET      /api/v1/ecritures/bilan/
GET      /api/v1/ecritures/compte_resultat/

GET/POST /api/v1/dimensions-analytiques/
GET/POST /api/v1/valeurs-analytiques/
GET/POST /api/v1/regles-evenements/
GET/POST /api/v1/events/
```

Les anciennes routes `/api/comptabilite/` restent disponibles pour compatibilité.

## Événements métier

Une application externe peut envoyer :

```json
{
  "type_evenement": "sale.completed",
  "source_system": "saheltech-platform",
  "source_type": "sale",
  "source_id": "SALE-001",
  "idempotency_key": "sale:SALE-001:v1",
  "payload": {
    "montant": "100000",
    "date": "2026-09-30",
    "libelle": "Vente projet",
    "compte_caisse": "571",
    "compte_produit": "701",
    "dimensions": {
      "PROJECT": "PROJ-19",
      "PHASE": "INSTALLATION",
      "MISSION": "MIS-44"
    }
  }
}
```

Le même `idempotency_key` ne crée jamais une seconde écriture pour la même entreprise.

## Comptabilité analytique

Le moteur utilise trois objets génériques :

```text
DimensionAnalytique
ValeurAnalytique
AffectationAnalytique
```

Exemple :

```text
Ligne : Transport 350 000 FCFA

PROJECT = PROJ-42
PHASE   = INSTALLATION
MISSION = MIS-8
```

Le moteur ne sait pas ce qu'est un `Project` Django. Il conserve uniquement la référence analytique.

## Traçabilité

Une écriture peut mémoriser :

```text
source_system
source_type
source_id
source_reference
idempotency_key
metadata
reversal_of
```

Cela permet de remonter d'une écriture vers l'opération source et de faire une vraie contre-passation.

## Intégration avec django-comptes

L'intégration est optionnelle.

`django-comptes` reste la source de vérité des mouvements de trésorerie.

`django-comptabilite-ohada` reste la source de vérité comptable.

Les transferts sont traités une seule fois et les annulations contre-passent l'écriture réellement liée au mouvement source.

## Multi-entreprise

Les données sont isolées par `entreprise_id`.

L'API dérive ce contexte de l'utilisateur authentifié au lieu d'accepter librement un identifiant d'entreprise envoyé par le client.

En mode standalone, `OrganisationComptable` et `AccesEntrepriseComptable` gèrent les appartenances locales. Si un utilisateur possède plusieurs entreprises, le client sélectionne le contexte avec le header `X-Enterprise-ID`.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Guide d'intégration API](docs/INTEGRATION_API.md)
- [Règles pour agents et développeurs](AGENTS.md)
- [Déploiement autonome](standalone/README.md)

## Tests

```bash
DJANGO_SETTINGS_MODULE=tests.settings python -m django check
DJANGO_SETTINGS_MODULE=tests.settings python -m django makemigrations --check --dry-run
DJANGO_SETTINGS_MODULE=tests.settings python -m django test comptabilite_ohada.tests -v 2
```

La CI exécute automatiquement ces contrôles sur les branches et pull requests.

## Licence

MIT
