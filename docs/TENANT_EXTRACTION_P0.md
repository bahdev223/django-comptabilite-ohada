# P0 : séparation du moteur comptable, multi-entreprise et écritures

## Règles de sécurité

1. Tout appel de service métier doit s'exécuter dans `tenant_scope(entreprise_id)` depuis un contexte de confiance, et toute requête doit être filtrée sur ce même identifiant.
2. Aucun identifiant fourni par un client ne vaut preuve d'appartenance ; l'hôte implémente `COMPTABILITE_OHADA["TENANT_RESOLVER"]` pour vérifier les droits réels (utilisateur, entreprise, rôle).
3. Les anciens signaux `django-comptes` sont interdits : encaissement ≠ vente ; décaissement ≠ charge ; transfert ≠ chiffre d'affaires. Leur activation provoque une erreur de configuration explicite.
4. Une écriture validée doit être équilibrée, rattachée à un exercice ouvert couvrant sa date et composée exclusivement de comptes/journaux du bon tenant.
5. Pour corriger une écriture validée, enregistrer une contrepassation dans un exercice ouvert autorisé ; jamais modifier silencieusement les lignes validées.
6. La synchronisation Cloud/Local ne peut pas deviner l'autorité d'une clôture : le contrat de synchronisation sera distinct, versionné et idempotent.

## Migration des données

Les anciens enregistrements peuvent avoir `entreprise_id=""`. Ne pas les rattacher à une société de façon automatique. Préparer un script de diagnostic et une opération humaine de réattribution avec preuves ; comparer balances/écritures sur une copie de base avant d'appliquer des contraintes NOT BLANK ou un basculement production.

## Rupture de compatibilité intentionnelle

L'API et les vues HTML historiques ne doivent pas être exposées sans contrôle d'accès tenant fiable. Les consommateurs migrent vers une API explicitement autorisée et des services de domaine prenant un contexte tenant. Les intégrations signal-based sont supprimées.

## Validation impérative avant merge

- `python manage.py check`, `python manage.py makemigrations --check --dry-run`
- Exécuter tous les tests Django puis PostgreSQL (deux sociétés avec mêmes codes de compte).
- Vérifier les routes de lecture/écriture, sélection de pièces et rapports, clôtures, contrepassations et transactions concurrentes.
- Tester les migrations sur copie, sauvegarde/restauration, et effectuer une revue des consommateurs Platform.
- Ne pas lancer GitHub Actions ni déployer sans autorisation.
