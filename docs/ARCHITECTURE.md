# Architecture cible

## Positionnement

`django-comptabilite-ohada` est un moteur comptable autonome et intégrable.

Il peut être :
1. installé comme app Django réutilisable ;
2. déployé seul via le projet `standalone` ;
3. appelé par SahelTech Platform ou n'importe quel ERP via API.

## Dépendances métier

Le moteur ne dépend d'aucun domaine métier.

```text
BTP / Solar / Services / ERP externe
               |
               v
        SahelTech Platform
               |
        événements métier
               |
               v
 django-comptabilite-ohada
     |                 |
     v                 v
comptabilité        analytique
```

## Modèle d'intégration

Une opération externe est identifiée par :
- entreprise ;
- système source ;
- type source ;
- identifiant source ;
- clé d'idempotence.

Les axes métier sont stockés comme dimensions analytiques :
- PROJECT ;
- PHASE ;
- MISSION ;
- SITE ;
- CONTRACT ;
- PROGRAM ;
- COST_CENTER ;
- etc.

Aucune FK métier n'est nécessaire.

## Événements

`EvenementMetier` joue le rôle d'inbox idempotente.

`RegleEvenementComptable` associe :
```text
type d'événement -> règle comptable
```

Cette association est configurable par entreprise.

## Comptabilité analytique

```text
DimensionAnalytique
        |
        v
ValeurAnalytique
        |
        v
AffectationAnalytique -> LigneEcritureComptable
```

Exemple :
```text
Ligne 6241 Transport 350 000
PROJECT = PROJ-42
PHASE = INSTALLATION
MISSION = MIS-8
```

## Déploiement

Pour utiliser le dépôt comme service autonome :
```bash
pip install -e ".[rest]"
python manage.py migrate
python manage.py runserver
```

Le contrat cible est `/api/v1/`.
