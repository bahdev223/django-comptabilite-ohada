# AGENTS.md — règles d'architecture

Ce dépôt est le moteur comptable OHADA générique de l'écosystème SahelTech.

## Frontière fondamentale

Le métier connaît la comptabilité. La comptabilité ne connaît jamais le métier.

Interdictions :
- aucune FK vers Projet, Chantier, Mission, Installation, Vente métier, etc. ;
- aucune condition du type `if domaine == "BTP"` dans le cœur comptable ;
- aucune duplication de logique de trésorerie propre à `django-comptes`.

Les intégrations utilisent :
- `source_system`, `source_type`, `source_id`, `source_reference` ;
- `idempotency_key` ;
- événements métier ;
- dimensions analytiques génériques.

## Sources de vérité

- Comptabilité générale : ce dépôt.
- Trésorerie : `django-comptes`.
- Projet : moteur projet externe.
- BTP/Solar/etc. : applications métiers externes.

## Invariants

Toute écriture validée doit :
- être équilibrée ;
- appartenir à une entreprise ;
- utiliser comptes/journal/exercice de la même entreprise ;
- avoir une date dans l'exercice ;
- ne pas être créée dans un exercice clôturé.

Une écriture validée se corrige par contre-passation, pas par suppression.

## Multi-entreprise

Toute lecture/écriture doit être scopée par `entreprise_id`.
Une API cliente ne doit pas pouvoir injecter un autre `entreprise_id`.

## Intégration

Préférer `POST /api/v1/events/` pour les applications externes.
Chaque événement externe doit avoir une clé d'idempotence stable.

## Tests

Toute modification d'un invariant critique doit ajouter un test de régression.
