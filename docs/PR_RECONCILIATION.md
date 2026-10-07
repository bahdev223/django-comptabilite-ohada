# Réconciliation des PR #1 et #2 — 7 octobre 2026

## Décision

Source de vérité : PR [#1](https://github.com/bahdev223/django-comptabilite-ohada/pull/1),
branche `fix/hardening-comptable-v1`. Reporter uniquement les écarts utiles de
[#2](https://github.com/bahdev223/django-comptabilite-ohada/pull/2).
Ne pas fusionner, cherry-pick ni rebaser le commit complet de #2.

La comparaison porte sur les HEAD réels `07fda4801e4eb02d12523a9a6b1315876a74fecd`
(#1) et `881175ca528ebcc6caab6fdbabb19257d1a3ef8d` (#2), tous deux basés sur
`main` à `4821545a331e44dfbcb073b37a30e4e51fa48c73`.

## Comparaison précise

| Domaine | PR #1 initiale | PR #2 | Contrat consolidé |
| --- | --- | --- | --- |
| Dimensions | DimensionAnalytique → ValeurAnalytique → AffectationAnalytique, tenant-scopées, axes libres, valeurs riches, ventilations pourcentage/montant | JSON `dimensions` par ligne, six axes fermés PROJECT/PHASE/ACTIVITY/TASK/MISSION/CONTRACT ; PROJECT obligatoire | Modèles normalisés de #1. Fusion des axes communs et par ligne ; contradiction refusée pour ECRITURE_GENERIQUE ; aucun JSON analytique concurrent |
| Ingestion | EvenementService → mapping RegleEvenementComptable → moteur → EcritureService ; ECRITURE_GENERIQUE reçoit déjà les lignes explicites | record_event crée directement une écriture validée puis bulk_create des lignes, source fixée à saheltech-platform/project | Pipeline de #1, brouillon puis validation atomique avec traçabilité, signaux et invariants. Aucun chemin de création parallèle |
| Contrôle des lignes | Équilibre, compte/exercice/tenant, immutabilité ; fallback code→PK, journal auto-créé/réactivé, précision générique peu stricte | Codes exacts, journal actif existant, montants finis positifs à deux décimales, limite 15 chiffres, champs bornés | Validation stricte pour les événements génériques, codes exacts et journal actif existant ; libellé de ligne limité à 200 caractères |
| Inbox/idempotence | EvenementMetier unique (entreprise_id, idempotency_key), reçu/audit/retry ; rejeu changé accepté silencieusement | IntegrationReceipt unique (entreprise_id, key), SHA-256 de toute enveloppe JSON, conflit 409 ; erreurs sans reçu | EvenementMetier seul. Comparaison JSON canonique des champs reconnus et du payload complet, sans nouvelle colonne ; 409 sur modification ; transaction/verrou de ligne incluant le traitement ; collision avec une écriture préexistante refusée |
| Erreurs/rejeu | ERREUR conservée, HTTP 422, retry explicite ; IGNORE si aucun mapping | HTTP 400 sur contenu/comptabilité invalides ; rejeu après clôture retourne le reçu | Politique d'audit/retry de #1 conservée. Rejeu exact après clôture fonctionne, sans revalider ni réactiver le journal ; seuls les appels nouveaux exécutent la règle |
| Coûts | Charges OHADA codes 6 et 81/83/85/87/89, écritures validées, filtres multiples/dates, fractions analytiques et contre-passations | Compte.nature=CHARGE, écritures validées, égalité JSON exacte, pas de ventilation ni filtres de dates | Agrégateur unique de #1 conservé. Montants HTTP décimaux textuels ; `currency` issue de ConfigurationComptable.devise du tenant, sinon DEVISE_PAR_DEFAUT/FCFA. Dates invalides/inversées : 400 |
| Réponse événement | Champs du reçu : id, statut, ecriture, etc. | entry_id, status=recorded | Champs #1 conservés + alias entry_id/status. TRAITE→recorded ; IGNORE→ignored ; ERREUR→error ; RECU→received |
| Authentification | ApplicationClienteComptable, secret haché SHA-256, préfixe indexé, organisation active, scopes ; X-API-Key ou Authorization: ApiKey | INTEGRATION_KEYS en clair dans settings, comparaison HMAC, pas de scopes/révocation/modèle client | Authentification #1 seule, scopes accounting.events.write/accounting.read ; challenge ApiKey pour 401, scope insuffisant 403 ; tenant porté par la clé, injection entreprise sans effet |
| Routes | API v1 complète et alias historique /api/comptabilite/ | Hôte ne montant que events et costs | API #1 conservée ; integration_urls optionnel expose uniquement POST events et GET costs en réutilisant EXACTEMENT les mêmes vues/services/permissions |
| Migrations | 0004 tenant scope → 0005 external_events_analytics → … → 0011 | 0003 → autre 0004 ajoutant JSON+IntegrationReceipt | Chaîne de #1 seule, fichiers inchangés. Ni migration de fusion ni nouvelle migration nécessaire |

## Compatibilité du client projet

1. Créer une OrganisationComptable et sa clé ApplicationClienteComptable avec
   `accounting.events.write` et `accounting.read` ; remplacer les anciennes clés
   INTEGRATION_KEYS dans la configuration du client. Aucun double backend d'auth.
2. Configurer la devise ISO (XOF au Mali) dans ConfigurationComptable du tenant.
3. Configurer le mapping `project.expense.created → ECRITURE_GENERIQUE` avant
   d'envoyer les événements. Un type non mappé retourne IGNORE/ignored et ne doit
   jamais être considéré comme comptabilisé par le client.
4. Préparer les comptes, le journal actif et l'exercice ouvert du tenant.
5. Conserver la même clé d'idempotence et la même enveloppe lors d'un rejeu.
   Une correction de données nécessite une nouvelle clé, et si nécessaire une
   contre-passation ; retry sert à corriger la configuration moteur, pas le payload.
6. Accepter 422 pour l'erreur comptable auditée, 409 pour le conflit, 401 pour la
   clé absente/invalide/révoquée et 403 pour les scopes insuffisants. `entry_id`
   n'est garanti que pour `status=recorded` / `statut=TRAITE`.
7. Lire total_cost/allocated_debit/allocated_credit comme décimaux textuels.
   Le prototype #1 les encodait en nombres JSON, #2 utilisait déjà des chaînes.

## Ordre de fusion

1. Relire et fusionner **uniquement la PR #1 consolidée** dans main. Le schéma
   déployé doit suivre 0001 → 0002 → 0003 → 0004_tenant_scope_configuration_assets_bank
   → 0005_external_events_analytics → 0006 → 0007 → 0008 → 0009 → 0010 → 0011.
2. Déployer ce moteur et configurer les clés, devises et mappings ; vérifier le
   client plateforme contre le contrat ci-dessus.
3. Fermer #2 comme remplacée par #1, sans la fusionner. Elle ne contient plus
   d'apport indépendant justifiant une seconde fusion.

Si une base a déjà appliqué la 0004 expérimentale de #2, sa situation est différente
de main ou de #1 : sauvegarder et inspecter migration ledger, reçus et JSON avant
de préparer une conversion de données vers l'inbox/affectations canoniques.
Cette tâche n'a pas d'accès à ces bases et ne prétend pas les avoir migrées.
Ne pas utiliser --fake pour masquer cette divergence.

## Écarts volontairement conservés et suites utiles

- Axes génériques libres plutôt que liste de six axes et contraintes de source
  codées en dur : la validation PROJECT/source_reference relève du producteur.
- Les ventilations sur plusieurs axes utilisent déjà le minimum des fractions
  demandées dans #1 ; c'est une hypothèse de hiérarchie, pas une distribution
  conjointe exacte pour axes indépendants. Un modèle de ventilation croisée serait
  un travail distinct, nécessaire seulement si le métier demande ce cas.
- Aucun ajout de payload_hash, IntegrationReceipt, champ JSON dimensions ni
  INTEGRATION_KEYS : ce seraient des doublons.

## Validation

Validation exécutée hors GitHub Actions avec Django 5.2.18, DRF 3.18.3 et SQLite :

| Vérification | Python 3.11.16 | Python 3.12.14 |
| --- | --- | --- |
| django check (settings de tests et standalone) | OK | OK |
| makemigrations --check --dry-run | Aucune dérive | Aucune dérive |
| Suite Django complète | 99/99 | 99/99 |
| Base neuve + toutes migrations | OK | OK |
| Montée 0003 → 0011 avec écriture historique et deux lignes | Conservées, feuille unique | Conservées, feuille unique |
| Parcours TCP hôte complet | PASS | PASS |
| Parcours TCP hôte restreint | PASS | PASS |

Les parcours HTTP utilisent un vrai serveur Django multithread sur 127.0.0.1 et
une base temporaire : ALPHA=125.00 XOF, BETA=80.00 XOF pour le même PROJECT et la
même clé ; rejeu simultané 201/200 avec entry_id identique ; rejeu modifié 409 ;
axes globaux conservés ; mauvais secret/révocation 401 ; scope lecture seule
403 ; injection d'entreprise sans effet ; contradiction analytique 422 sans
écriture ; contre-passation ALPHA→0.00 et BETA inchangé ; rejeu après clôture ;
routes d'administration et historiques 404 sur l'hôte restreint.

La suite comprend trois cas de concurrence sur connexions distinctes : réception
identique, réception modifiée et retry simultané. La revue indépendante a révélé
et les tests ont reproduit avant correction : collision d'axes par casse/type,
verrouillage SQLite concurrent et course avec une écriture préexistante. Les
corrections ont été suivies d'une nouvelle exécution complète sur les deux Python.
Sous SQLite, la réservation d'écriture précède la lecture, les contentions sont
retentées hors transaction hôte avec une borne temporelle ; si le stockage reste
occupé, l'API retourne 503/Retry-After: 1. Rejouer la même enveloppe et clé.

Commandes reproductibles, avec chaque interpréteur dans un environnement isolé :

```bash
DJANGO_SETTINGS_MODULE=tests.settings python -m django check
DJANGO_SETTINGS_MODULE=tests.settings python -m django makemigrations --check --dry-run
DJANGO_SETTINGS_MODULE=tests.settings python -m django test comptabilite_ohada.tests -v 1
python scripts/verify_migration_path.py
python scripts/verify_project_http.py
python scripts/verify_project_http.py --restricted
```

Limites : aucune base de production ni migration expérimentale #2 n'a été
inspectée. PostgreSQL n'a pas été exécuté dans cette session ; la preuve de
concurrence porte sur SQLite. Les verrous de ligne PostgreSQL doivent être
validés sur le runtime PostgreSQL du déploiement avant de revendiquer cette
compatibilité de concurrence. Aucun run GitHub Actions n'a été lancé ; les commits
de réconciliation utilisent `[skip ci]` conformément à la consigne utilisateur.
