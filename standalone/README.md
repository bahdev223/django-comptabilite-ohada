# Déploiement autonome

Ce dossier transforme le package `django-comptabilite-ohada` en service Django autonome sans coupler le moteur à un ERP métier.

## Développement

```bash
pip install -e ".[rest]"
python manage.py migrate
python manage.py charger_plan_comptable
python manage.py runserver
```

API cible :

```text
/api/v1/
```

L'application reste parallèlement installable comme simple app Django dans un autre projet.
