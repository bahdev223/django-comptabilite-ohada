# django-comptabilite-ohada — moteur SYSCOHADA

Bibliothèque Django de comptabilité en partie double : plan comptable, journaux, écritures, exercices, balance, grand livre, reporting et fonctionnalités auxiliaires.

**Statut de cette branche : sécurisation P0 proposée, non fusionnée, non publiée en version et non validée sur PostgreSQL.** La présence de services comptables ne constitue pas une certification SYSCOHADA.

## Séparation de SahelTech

- Moteur canonique candidat : ce dépôt.
- Service autonome : [saheltech-comptabilite](https://github.com/bahdev223/saheltech-comptabilite) (backend Django/DRF, base PostgreSQL indépendante, Accounts et interface à construire).
- Les applications métiers gardent les caisses, encaissements, factures et paiements opérationnels.

## Règles P0

- Chaque opération de la bibliothèque reçoit `entreprise_id=` explicite, issu d'un contexte d'entreprise **autorisé côté serveur**.
- Un compte, un journal, un exercice et toutes les lignes d'une écriture appartiennent au **même** tenant ; période ouverte et montants Decimal, débit=crédit.
- Une écriture validée ne se modifie pas, elle se contre-passe avec motif.
- Les anciennes API/HTML sont bloquées ; ne pas monter leurs ViewSets.
- Les signaux automatiques de `django-comptes` sont désactivés : encaissement ≠ vente, transfert ≠ produit.
- La clôture automatique et la réouverture sont suspendues en attendant la revue métier et l'autorité Cloud/Local.
- Les lignes historiques sans entreprise sont conservées, sans attribution automatique.

Exemple d'utilisation côté hôte **après vérification du droit d'entreprise** :

```python
from comptabilite_ohada.services.ecriture_service import EcritureService

compte = EcritureService.get_compte("571", entreprise_id=entreprise_verifiee)
```

Les anciens appels sans `entreprise_id` échouent volontairement. Ne pas utiliser la branche pour un hôte historique sans adaptateur et reprise des données.

## Tests et migrations

Migrations additives 0004/0005 fournies, à tester sur une **copie** PostgreSQL. Les tests SQLite (52) rapportés lors du correctif initial sont **antérieurs aux dernières modifications**.

Nouveaux tests PostgreSQL : `comptabilite_ohada/tests/test_postgres_concurrency.py`, à exécuter avec les recettes du dépôt de service.

Guide : [docs/P0_REMEDIATION.md](docs/P0_REMEDIATION.md).

Aucune fusion, GitHub Actions volontaire, migration de production ni déploiement n'est autorisé pour cette branche.

## Inventaire des lignes historiques sans entreprise

Sur une copie de recette migrée en 0005, lancer `python manage.py audit_tenant_isolation --fail-on-anomaly`. La commande est en lecture seule, aucun rattachement automatique de tenant n'est accepté.
