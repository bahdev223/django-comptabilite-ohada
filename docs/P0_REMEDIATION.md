> Recette actualisée du 12 octobre : voir REVIEW_2026-10-12.md. PostgreSQL reste bloqué ; aucune activation.

# Audit et corrections P0 — 11 octobre 2026

## Sources figées

- Moteur canonique : `bahdev223/django-comptabilite-ohada`, main `4821545a331e44dfbcb073b37a30e4e51fa48c73`.
- Service autonome : PR #1, `fe159bb4460c09a87eac8560433f774cc364696b`.
- Copie Platform : `codex/platform-bootstrap`, `78607a28c19c8181163ce3bad717d9afac79cab2`.
- Périmètre comparé hors caches et gabarits : 66 fichiers moteur, 30 copie, 14 identiques, 16 divergents. Les 16 contenus et diffs ont été examinés. Aucun fichier Platform copié aveuglément.

## Revue des 16 divergences

| Chemin relatif | Différence constatée | Décision |
| --- | --- | --- |
| `__init__.py` | Alias sys.modules du namespace natif Platform | Conserver namespace canonique, pas d'alias global |
| `apps.py` | AppConfig natif avec label historique identique | Conserver AppConfig canonique et label/migrations |
| `defaults.py` | Import settings inutilisé retiré dans Platform | Pas de changement métier à récupérer ; désactiver les drapeaux automatiques du canonique |
| `integrations/__init__.py` | Pont comptes désactivé par défaut dans Platform | Reprendre le principe ; faux par défaut et erreur de configuration si réactivation du pont dangereux |
| `integrations/django_comptes.py` | Imports natifs ; mêmes mauvaises imputations | Ne reprendre aucune imputation ; suspendre le pont, aucun receiver enregistré |
| `models/__init__.py` | Ordre/imports reformatés, exports identiques | Garder exports canoniques |
| `models/amortissement.py` | Ordre imports | Aucune amélioration métier ; ajouter tenant et unicité tenant/code sans attribuer l'historique |
| `models/ecriture.py` | Import settings inutilisé retiré | Sécuriser le canonique ; pas d'écart métier utile |
| `services/__init__.py` | Copie omet DashboardService et ExportService | Garder les exports publics canoniques |
| `services/amortissement_service.py` | Import Decimal retiré | Aucun correctif métier ; génération suspendue avant audit calendaire/arrondis/idempotence |
| `services/bilan_service.py` | Imports/variables reformatés | Garder calculs sans les certifier SYSCOHADA ; filtrage tenant ajouté |
| `services/ecriture_service.py` | Imports/reformatages, f-strings fixes | Même fuite de tenant ; correction du canonique requise |
| `services/exercice_service.py` | Platform ajoute l'import Sum manquant | Retenir cette correction ; ajouter verrouillage, contrôles et agrégats nets tenant-scoped |
| `services/initialisation_service.py` | Imports date déplacés, reformatages | Même suppression globale et singleton ; corriger sans suppression de données |
| `services/journal_service.py` | Imports/variables reformatés | Garder canonique avec filtrage tenant des rapports et références |
| `services/rapprochement_service.py` | Imports inutilisés retirés | Aucun correctif métier ; service suspendu avant validation |

Les migrations 0001–0003 et les modèles comptes/journaux/exercices/configuration de la copie sont identiques dans le périmètre comparé. La copie a moins de fichiers : son absence d'API, de vues ou de tests n'est pas une preuve de sécurité.

## P0 corrigés ou contenus

- `entreprise_id` explicite requis dans saisie, recherche de comptes/exercices/journaux, initialisation et rapports. FK relues en base et vérifiées dans le même tenant ; les lignes de rapports excluent aussi les graphes historiques incohérents.
- Partie double exacte en Decimal ; montants finis, non négatifs, maximum 15 chiffres dont 2 décimales, pas d'arrondi implicite ; au moins deux lignes, exactement une colonne positive par ligne ; refus journal inactif, compte inactif, exercice clos/hors dates.
- Création/validation sérialisées sur exercice ; clôture automatique désormais suspendue ; ajout de lignes sérialisé sur exercice puis écriture. Mutations/suppressions directes et bulk ORM des écritures/lignes rejetées. Seul le service de validation marque l'écriture validée après contrôle des lignes persistées.
- Références comptes/journaux/exercices protégées contre suppression en cascade (`PROTECT`). Rechargement `force` du plan fait un update_or_create par entreprise, jamais une suppression des comptes ou écritures.
- Configuration par entreprise ; nouvelle unicité configuration non vide et immobilisation par tenant/code. Relevés bancaires reçoivent un champ tenant pour future remédiation.
- Pont signaux comptes désactivé par défaut et irréactivable en l'état. Aucun encaissement/transfert automatiquement assimilé à vente/charge. Nouveau règlement exige contrepartie explicite hors vente/transfert ; transfert exige deux comptes de trésorerie distincts.
- Contrepassation avec motif, références source stables, original conservé, répétition rejetée. Exercice ouvert correspondant à la date de contrepassation requis. Les agrégats dashboard et calculs préparatoires de clôture tiennent compte des débits des produits et crédits des charges : une vente contrepassée ne laisse pas de bénéfice fictif.
- Injection `configuration_id`/`id` dans les soldes initiaux refusée par liste blanche ; montants validés avant écriture.
- Statut staff/superuser ne donne plus implicitement un droit comptable. Le moteur reçoit un contexte déjà autorisé ; l'app hôte reste responsable des appartenances actives et rôles locaux.
- Les anciens ViewSets refusent toutes les requêtes, y compris superuser. Serializers historiques de création bloqués ; représentations explicites ; champ de ligne `sens` inexistant retiré. Aucune route HTML historique enregistrée.
- Amortissements et rapprochement suspendus explicitement ; ils ne sont pas déclarés sécurisés ou extraits.

## Conservation et compatibilité

Migrations moteur 0004/0005 additives ; aucune migration historique modifiée, aucune ligne supprimée, aucun tenant deviné. Les nouvelles colonnes restent vides pour les anciennes configurations, immobilisations et relevés. Les comptes/écritures historiques sans tenant restent en base mais les services sécurisés ne les servent pas et ne les modifient pas. Un test MigrationExecutor 0003→0005 vérifie IDs, montants, validation et absence d'attribution automatique, y compris une écriture historique incohérente : elle est conservée, pas « corrigée » arbitrairement.

Le label Django, noms de modèles, tables et exports publics sont conservés. Le contrat Python devient volontairement strict : passer `entreprise_id=` partout ; aucun tenant global de secours. Ce changement n'est pas compatible avec les appels historiques non scopés. Ne pas mettre à jour un hôte existant sans adaptateur, désactivation du pont et tests des contrats sources. La copie Platform reste inchangée. Aucune base ou opération des services source n'a été touchée.

Rollback : tant qu'aucune donnée nouvelle n'est créée, tester le retour de schéma sur copie. Après des immobilisations partageant un code entre tenants, le retour à l'unicité globale peut échouer : privilégier rollback applicatif avec schéma conservé ou restauration d'une sauvegarde vérifiée. Ne pas supprimer les colonnes tenant ou réinstaller l'ancien moteur en production sans procédure de reprise.

## Validation exécutée

Python 3.12, Django 5.2.18, DRF 3.18.3, psycopg 3.3.6. Dépendances installées localement ; ce ne sont pas des attestations des images de production.

| Contrôle | Résultat |
| --- | --- |
| Baseline moteur | 20 tests SQLite réussis avant modification |
| Baseline PR #1 | 13 tests SQLite réussis |
| Suite moteur finale | 52 tests SQLite réussis, dont migration de conservation |
| Backend + adaptateur d'extraction | 19 tests SQLite réussis (13 socle + 6 intégration) |
| Django check | Sans erreur, moteur et backend |
| makemigrations --check --dry-run | Sans divergence après migrations ajoutées |
| PostgreSQL moteur et backend | Tentatives effectuées ; connexion 127.0.0.1:5432 refusée, aucune suite Pg exécutée |
| JWT/JWKS Accounts réel | Non exécuté ; tests existants simulés uniquement |
| GitHub Actions, fusion, déploiement, migrations réelles | Aucun |

L'installation locale d'un serveur PostgreSQL n'a pas abouti dans cet environnement. Aucun identifiant ni accès à une base de recette n'a été fourni. Les tests SQLite ne prouvent ni verrous SELECT FOR UPDATE, ni concurrence, ni comportement SQL PostgreSQL.

## Extraction limitée

Le service reçoit un adaptateur interne `tenancy.engine_gateway` : création centrale d'écriture et lecture balance seulement. Il revalide le compte actif, l'appartenance et le rôle, fixe tenant/créateur côté serveur et refuse les champs serveur du payload. Aucune URL ajoutée. `ACCOUNTING_ENGINE_VALIDATED` reste faux ; le moteur ne rejoint pas INSTALLED_APPS ni requirements de production. Le module `accounting_service.engine_test_settings` n'est utilisable que pour les tests opt-in avec la source canonique sur PYTHONPATH. Aucun appel comptes/finance source ni signal métier raccordé.

## Bloquants avant fusion/activation

1. Exécuter suites et migrations sur PostgreSQL isolé ; ajouter recette concurrente validation/ajout de ligne/clôture/contrepassation et collisions de références. Tester backup/restore et migration sur copie réaliste, avec rapprochement des balances et graphes FK.
2. Valider le contrat réel Accounts : access tokens opaques à introspecter sur un endpoint serveur authentifié (saheltech-identity PR de préparation), issuer/client_id/sub/scope/expiration/révocation et rôles locaux ; la PR ne prouve pas le raccordement au fournisseur réel.
3. Inventorier l'historique sans tenant et FK incohérentes ; plan de rattachement approuvé fondé sur pièces sources, sans rattachement par email ou tenant arbitraire. Durcissement DB après cette remédiation seulement.
4. Épingler une révision canonique validée puis définir l'API nouvelle tenant-scoped et son contrat de saisie. Les états financiers ne sont pas certifiés SYSCOHADA par ces seuls tests ; revue métier (bilan, paie, TVA, clôture, comptes de paiement) requise.
5. Inbox/outbox versionnées, idempotence événement source, reprise/annulation/rapprochement. L'unicité référence et la contrepassation stable ne remplacent pas une inbox d'événements.
6. Contrats de compatibilité avec Platform/Transport/Commerce/RH et autres sources, recettes Cloud/Local, autorité de clôture, conflits offline et rollback.
7. Audit métier et tests propres aux amortissements/rapprochement avant lever leur suspension ; réouverture d'exercice reste refusée avant procédure autorisée de contrepassation de clôture.

**Décision : changements proposés pour revue en brouillon ; pas de fusion ni activation opérationnelle à ce stade.**


## Intervention complémentaire du 12 octobre 2026 (non testée)

- Le lookup d'un code SYSCOHADA fourni en chaîne ne se transforme plus silencieusement en PK Django : un entier est un identifiant, une chaîne est un code.
- Les signaux ecriture_validee sont différés via transaction.on_commit pour ne pas publier un écrit en cas de rollback ; le protocole outbox/inbox reste à développer.
- Clôture automatique historique **désactivée par défaut et actuellement refusée** : l'imputation simplifiée du résultat au capital n'a pas reçu de validation SYSCOHADA, et l'autorité Cloud/Local n'est pas définie.
- Trois nouveaux tests PostgreSQL TransactionTestCase vérifient verrou de l'exercice, validation concurrente et références répétées, mais **ils n'ont pas encore été exécutés**.
- SahelTech Comptabilité fournit désormais un Docker Compose de recette PostgreSQL 16 manuel, sans publication de port, qui réunit les deux dépôts voisins. Consulter docs/POSTGRES_RECETTE.md de saheltech-comptabilite PR #1.
- La PR #3 du même dépôt contient une implémentation alternative des migrations 0004/0005 : **ne pas fusionner les deux branches ensemble**. La PR #4 est la candidate principale après recette.

Les 52 tests SQLite déclarés sont antérieurs à cette intervention complémentaire ; ne pas présenter ces nouveaux correctifs comme validés sans relancer la suite complète. Aucun test PostgreSQL n'est attesté dans ce nouveau travail.

## Diagnostic des données historiques (commande réutilisée de la PR #3)

La commande `python manage.py audit_tenant_isolation --fail-on-anomaly` est disponible sur cette branche. Elle recense, **sans jamais les modifier**, les lignes sans entreprise, les références interentreprises (journal/exercice/ligne de compte/parent) et les configurations en doublon. L'exécution doit se faire **sur copie PostgreSQL restaurée** en priorité ; elle échoue volontairement si une anomalie existe avec --fail-on-anomaly.

Un test de non-modification a été ajouté en branche, sans être exécuté dans cette session.
