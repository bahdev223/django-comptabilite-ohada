# Directives agents — django-comptabilite-ohada

Bibliothèque métier SYSCOHADA canonique candidate pour SahelTech Comptabilité.

## Invariants de sécurité P0
- Aucun accès HTTP sans identité, permission de modèle Django et résolution d'appartenance entreprise côté serveur.
- Tout service ou traitement de fond utilise un tenant_scope(entreprise_id) explicite.
- Ne jamais lire ou écrire des comptes, journaux, exercices, écritures, immobilisations, relevés, rapports et exports sans filtrage entreprise.
- L'API historique et les vues HTML non sécurisées restent désactivées ; ne pas les réactiver en contournant le résolveur.
- Un encaissement n'est pas nécessairement une vente et un transfert n'est jamais un produit.
- Aucune écoute directe des signaux django-comptes : les événements interservices doivent être qualifiés, signés/authentifiés, idempotents et traçables.
- Validation comptable via ValidationService et contrepassation, jamais par modification directe d'une écriture validée.
- La clôture/réouverture d'exercice reste bloquée jusqu'à revue métier SYSCOHADA et définition de l'autorité Cloud/Local.
- Examiner les anciennes données sans entreprise_id, ne jamais les assigner arbitrairement.
- Interdiction d'utiliser GitHub Actions, déployer ou fusionner sans accord.

## Tests/recette indispensables
\`python -m compileall -q comptabilite_ohada\`
\`python manage.py check\` dans un hôte Django 5.2 + DRF
\`python manage.py makemigrations --check --dry-run\`
\`python manage.py test comptabilite_ohada.tests\` avec PostgreSQL
Comparer la balance sur copie de données, vérifier les tenants A/B, transactions concurrentes et retour arrière.

Ne pas déclarer "prêt pour production" avant exécution réelle des contrôles.
