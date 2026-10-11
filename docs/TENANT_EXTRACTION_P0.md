# Audit d'extraction P0 — SahelTech Comptabilité

Branche : \`fix/tenant-isolation-accounting-p0\`. Référence source : \`main\` du moteur \`django-comptabilite-ohada\`.

## Changements réalisés dans la branche

- Contexte de société obligatoire via \`comptabilite_ohada.tenancy.tenant_scope\`.
- Recherche tenant-scoped de comptes, journaux, exercices, écritures, immobilisations, configurations et relevés.
- Validation comptable : comptes actifs/mouvementables, exercice ouvert et couvrant la date, au moins deux lignes, débit = crédit, montant Decimal positif, transactions atomiques.
- Validation sous verrou d'exercice, contrepassation à référence stable dans un exercice ouvert.
- Suppression des récepteurs de signaux \`django-comptes\` : aucun encaissement ou transfert n'est automatiquement assimilé à une vente.
- API DRF : utilisateur authentifié, permissions Django par modèle, resolver d'appartenance entreprise fourni par l'hôte et filtrage sur toutes les lectures.
- Vue HTML historique désenregistrée ; API inactive sans opt-in.
- Rapports, exports, sélecteurs, relevés, amortissements et initialisation limités au tenant actif.
- Modèles auxiliaires multi-entreprise ; FKs comptables PROTECT ; migration 0004/0005.
- Données préexistantes avec \`entreprise_id=""\` **quarantinées**, pas réattribuées automatiquement.
- Clôture/réouverture désactivées avant revue métier SYSCOHADA/Cloud-Local.
- Tests multi-entreprises rédigés mais encore non exécutés.

## Décisions irréversibles interdites pour l'instant

- Aucune migration en production sans essais PostgreSQL sur sauvegarde/restauration.
- Aucun export ou réaffectation automatique d'anciennes lignes sans preuve de rattachement à une société.
- Aucune activation des anciens signaux ou vues HTML par une simple option.
- Aucun déploiement, fusion ou GitHub Actions sans autorisation explicite.

## Procédure pour les données historiques

1. Copier et restaurer une base non productive, avec inventaire du nombre d'écritures et soldes par entreprise connue.
2. Appliquer 0004/0005 sur la copie et lancer \`audit_tenant_isolation --fail-on-anomaly\`.
3. Construire un mapping audité \`ancien ID / entreprise métier / preuve / nouvelle entreprise_id\`.
4. Corriger les croisements de sociétés en conservant l'historique et les justificatifs (pas de suppression silencieuse).
5. Recalculer balance, grand livre et résultat avant/après ; comparer les sommes par entreprise et exercice.
6. Tester les permissions HTTP (GET, POST, actions), annulations répétées, références et verrous PostgreSQL.
7. Écrire un rollback puis seulement décider d'une mise en production.

## Points restant bloquants

- Tests Django/PostgreSQL et contrôle de cohérence des migrations **non exécutés**.
- Analyse métier validée de la clôture / réouverture, calcul de résultat et obligations SYSCOHADA.
- Raccordement réel à SahelTech Accounts via une API du nouveau service, pas la bibliothèque seule.
- Convergence des 16 fichiers divergents du moteur avec la copie Platform.
- Contrat d'intégration d'événements interservices / outbox-inbox / idempotence et mode offline.
- Audit du plan comptable et des données locales existantes.
- UX React de la nouvelle application.

Ce correctif privilégie un défaut fermé plutôt qu'une comptabilisation silencieuse ou une lecture inter-entreprises.
