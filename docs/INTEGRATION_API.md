# Guide d'intégration API

## Authentification

En mode standalone :

```text
POST /api/v1/auth/token/
```

avec `username` et `password`.

Puis :

```http
Authorization: Token <token>
```

## Sélection de l'entreprise

```text
GET /api/v1/organisations/
```

Si l'utilisateur possède plusieurs entreprises, envoyer ensuite :

```http
X-Enterprise-ID: ENT-A
```

Le serveur vérifie que l'utilisateur possède réellement un accès à cette entreprise.

## Principe

Les ERP externes devraient préférer l'ingestion d'événements plutôt que construire directement les écritures.

Endpoint :

```text
POST /api/v1/events/
```

## Exemple

```json
{
  "type_evenement": "sale.completed",
  "source_system": "saheltech-platform",
  "source_type": "sale",
  "source_id": "SALE-001",
  "idempotency_key": "sale:SALE-001:v1",
  "payload": {
    "montant": "100000",
    "date": "2026-09-30",
    "libelle": "Vente projet",
    "compte_caisse": "571",
    "compte_produit": "701",
    "dimensions": {
      "PROJECT": {
        "code": "PROJ-19",
        "libelle": "Projet Sikasso"
      },
      "PHASE": "INSTALLATION",
      "MISSION": "MIS-44"
    }
  }
}
```

## Idempotence

Le même `idempotency_key` pour une entreprise retourne l'événement existant et ne crée pas une seconde écriture.

Un événement dont le traitement comptable échoue reste enregistré avec le statut `ERREUR` pour audit. L'écriture partielle est annulée par transaction.

## Mapping

Avant traitement, configurer :

```text
type_evenement = sale.completed
code_regle     = VENTE_COMPTANT
```

via `/api/v1/regles-evenements/`.

## Ressources analytiques

```text
GET/POST /api/v1/dimensions-analytiques/
GET/POST /api/v1/valeurs-analytiques/
```

## Traçabilité

Chaque écriture peut conserver :
- `source_system`
- `source_type`
- `source_id`
- `source_reference`
- `idempotency_key`
- `metadata`
- `reversal_of`

## Compatibilité

Les anciennes routes `/api/comptabilite/` restent disponibles.

## Contrat analytique consolidé (#1 + apports utiles de #2)

L'authentification machine-to-machine utilise exclusivement
`ApplicationClienteComptable.generer_cle(organisation, nom, scopes)` avec
`accounting.events.write` pour POST events et `accounting.read` pour GET costs.
Le secret est retourné une seule fois et seul son hash est conservé. Envoyer
`X-API-Key` ou `Authorization: ApiKey <secret>` ; le tenant vient de la clé.
`INTEGRATION_KEYS` n'est pas pris en charge.

Pour un producteur qui fournit ses lignes, créer le mapping
`project.expense.created → ECRITURE_GENERIQUE`. Ce mapping est administré côté
moteur ; sans mapping l'événement est `IGNORE`, pas comptabilisé. Date explicite,
comptes par codes exacts, journal actif existant et exercice ouvert sont requis.
Les dimensions communes sont héritées par les lignes, qui peuvent ajouter des
axes mais ne doivent pas contredire les axes communs. Les ventilations et valeurs
riches du moteur restent utilisables ; les axes ne sont pas limités au projet.

Le POST retourne les champs de l'inbox ainsi que `entry_id` et `status` :
`TRAITE/recorded`, `IGNORE/ignored`, `ERREUR/error` ou `RECU/received`.
Un rejeu identique retourne 200 et le même reçu, même après clôture ; une nouvelle
réception retourne 201. Modifier type/source/payload pour une clé déjà reçue
retourne 409, sans changer le reçu ni l'écriture. Une erreur comptable retourne
422 et conserve le reçu pour audit/retry ; JSON invalide retourne 400, clé absente
ou invalide 401, scopes insuffisants 403. La transaction englobe inbox et traitement.

`GET /api/v1/analytics/costs/?PROJECT=PRJ-001&PHASE=INSTALLATION` retourne notamment
`total_cost`, `allocated_debit`, `allocated_credit` sous forme décimale textuelle,
`line_count`, les dimensions et `currency`. Devise : ConfigurationComptable du
TENANT, sinon DEVISE_PAR_DEFAUT, sinon FCFA. Configurer XOF explicitement au Mali.
Les filtres `date_debut` et `date_fin` sont des dates ISO ; une période inversée
est refusée. Les charges validées et leurs contre-passations déterminent le coût net.

Les réceptions et retry simultanés réutilisent le même reçu. Sous SQLite, une
contention persistante retourne 503 avec `Retry-After: 1` ; rejouer alors la même
clé et la même enveloppe. Les transactions appartenant au projet hôte ne sont
jamais redémarrées automatiquement par le moteur.

Pour un hôte dédié limité à ces deux opérations, monter
`comptabilite_ohada.integration_urls` comme ROOT_URLCONF, avec les mêmes réglages
DRF et la même authentification que standalone.settings. Cet hôte ne monte ni
les ressources administratives v1 ni les alias historiques ; aucun service ou
modèle comptable distinct n'est introduit.

Le comparatif détaillé, les différences de contrat, les précautions pour une
base expérimentale #2 et l'ordre de fusion sont dans [PR_RECONCILIATION.md](PR_RECONCILIATION.md).
