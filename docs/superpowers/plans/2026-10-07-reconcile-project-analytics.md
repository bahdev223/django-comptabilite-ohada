# Réconciliation du contrat analytique — Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolider les PR #1 et #2 sur fix/hardening-comptable-v1 avant toute fusion.

**Architecture:** Conserver EcritureService, EvenementMetier et les affectations analytiques normalisées de #1. Reporter les apports utiles de #2 sans seconde inbox, JSON analytique sur les lignes, authentification INTEGRATION_KEYS ni migration concurrente.

**Tech Stack:** Django 5.2, DRF, Python 3.11 et 3.12, SQLite ; validation HTTP locale.

**Spec:** Demande du 7 octobre 2026 ; comparaison figée des HEAD 07fda480 et 881175ca, documentée dans docs/PR_RECONCILIATION.md.

## Global Constraints

- Ne pas fusionner main pendant cette tâche ; rendre la branche #1 prête à la revue.
- Respecter AGENTS.md : moteur générique, aucune FK métier, scope entreprise obligatoire.
- Conserver une chaîne de migrations 0001–0011 ; ne pas importer la 0004 de #2.
- Tests hors GitHub Actions ; commits avec [skip ci].

## Review Focus

- Rejeu modifiant type, source ou payload : HTTP 409, aucune nouvelle écriture.
- Dimensions communes et spécifiques : fusion sans perte, contradiction refusée.
- Montants non finis, précision excessive et compte numérique inexistant : refus atomique.
- Clé étrangère, révoquée ou scopes insuffisants : aucun accès interentreprise.
- Rejeu après clôture et requêtes concurrentes : même reçu, aucune double écriture.

### Task 1: Consolidation de l'ingestion et de l'API

**Files:** services/evenement_service.py, rules/generique.py, api/views.py, api/serializers.py, authentication.py, integration_urls.py, tests/test_project_integration.py.

**Interfaces:** EvenementService.recevoir retourne (EvenementMetier, created) ; une collision sur l'enveloppe existante lève IdempotencyConflict. Les endpoints gardent leur contrat #1, ajoutent entry_id/status et currency pour le client #2. Les routes restreintes réutilisent exactement les mêmes vues/services et clés hachées.

- [x] Ajouter les scénarios HTTP de #2 adaptés à la clé hachée et au mapping ECRITURE_GENERIQUE, puis les cas critiques de Review Focus.
- [x] Exécuter les nouveaux tests et constater les échecs attendus avant modification.
- [x] Implémenter comparaison d'enveloppe stockée, verrouillage transactionnel, fusion des axes, validation stricte des lignes et surface restreinte.
- [x] Rejouer tests ciblés et suite existante.

### Task 2: Validation et livraison

**Files:** docs/PR_RECONCILIATION.md, docs/INTEGRATION_API.md, scripts/verify_project_http.py, tests si un défaut est découvert.

**Interfaces:** Utilise la branche consolidée de Task 1 ; publie preuve des commandes exécutées et ordre exact de fusion.

- [x] Exécuter check, makemigrations --check --dry-run, migrations et suite complète avec les deux interpréteurs.
- [x] Vérifier montée depuis 0003 et nouvelle base ; une seule feuille du graphe.
- [x] Vérifier le parcours HTTP réel : ALPHA/BETA, coût exact, idempotence, conflit, scopes, révocation, contre-passation et routes restreintes.
- [x] Faire une revue indépendante des modifications et corriger les défauts critiques avec tests RED→GREEN.
- [ ] Publier le commit sur #1 sans Actions et actualiser les descriptions de PR. Ordre : fusion #1 consolidée, fermeture #2 comme remplacée ; aucune fusion de #2.
