# Directives agents — Moteur OHADA

Ce dépôt reste un package Django réutilisable, pas le serveur SahelTech Comptabilité.

## Sécurité obligatoire
- Passer entreprise_id depuis une appartenance contrôlée côté serveur ; ne jamais inférer d'un header seul.
- Vérifier tenant sur les objets liés, services, commandes, états, exports et fonctions secondaires.
- Écritures : partie double exacte en Decimal, exercice ouvert sur la date, compte et journal actifs.
- Pas de modification directe d'écritures validées, utiliser contrepassation auditée.
- Refuser toutes les intégrations par signaux django-comptes héritées.
- L'API historique reste bloquée, comme amortissements/rapprochements non certifiés.
- Suspendre la clôture et la réouverture jusqu'à validation SYSCOHADA/Cloud-Local.

## Recette bloquante
- PR #4 prioritaire ; ne PAS fusionner la PR #3 ni ses migrations alternatives.
- Tester la suite SQLite actuelle, puis PostgreSQL 16, concurrence et migration 0003→0005.
- Vérifier l'historique sans entreprise sur une copie restaurée ; rapprochement écritures/balances par tenant.
- Pas de GitHub Actions sans autorisation, de fusion ou de déploiement sans recette.
- Documenter toutes les différences entre tests écrits, tests exécutés et fonctionnalités activées.

Voir docs/P0_REMEDIATION.md et le protocole PostgreSQL du nouveau service.
