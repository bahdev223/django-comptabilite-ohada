# Guide d'intégration API

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
