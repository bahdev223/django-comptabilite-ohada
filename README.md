# django-comptabilite-ohada

Bibliothèque Django pour la comptabilité OHADA/SYSCOHADA en partie double. Cette bibliothèque fournit le **moteur métier candidat** pour le nouveau service autonome [SahelTech Comptabilité](https://github.com/bahdev223/saheltech-comptabilite).

> **Attention : branche de sécurité en cours de recette.** Les changements P0 sont susceptibles de rompre les anciens consommateurs ; ne pas fusionner/déployer avant les contrôles listés ci-dessous.

## Capacités métier

Plan SYSCOHADA, journaux, exercices, écritures équilibrées, grand livre, balance, bilan, résultat, rapprochement et immobilisations. La présence du code ne vaut pas certification comptable ; la clôture/réouverture est volontairement bloquée jusqu'à revue spécialisée.

## Changement de sécurité : tenant obligatoire

Chaque entreprise conserve ses comptes, journaux, exercices, écritures, rapports et configurations, avec référence explicite et non vide. Pour un job ou un service **côté serveur** :

\`\`\`python
from comptabilite_ohada.tenancy import tenant_scope
from comptabilite_ohada.services.ecriture_service import EcritureService

# ID de société validé par l'application hôte, jamais repris aveuglément
# depuis un header non autorisé.
with tenant_scope(entreprise_id_verifie):
    compte = EcritureService.get_compte("571")
\`\`\`

Le paquet ne choisit plus arbitrairement un exercice ouvert et refuse une écriture hors période. Une écriture validée ne peut pas être modifiée ou supprimée via les méthodes de modèle usuelles. Les correctifs passent par une contrepassation dans un exercice ouvert.

## Sécurité HTTP

Les anciennes vues HTML non cloisonnées ont été retirées de \`comptabilite_ohada.urls\`. L'API DRF est **désactivée par défaut**.

Pour exposer une API :

\`\`\`python
INSTALLED_APPS += ["rest_framework", "comptabilite_ohada"]
COMPTABILITE_OHADA = {
    "API_ENABLED": True,
    "TENANT_RESOLVER": "myapp.security.resolve_accounting_tenant",
    "COMPTES_INTEGRATION_ENABLED": False,
    "STOCK_INTEGRATION_ENABLED": False,
}
\`\`\`

Le resolver \`resolve_accounting_tenant(request)\` doit authentifier l'utilisateur, vérifier son appartenance **réelle** à l'entreprise demandée et renvoyer son identifiant stable. Le moteur applique ensuite une vérification d'autorisation Django **sur toutes les méthodes, GET compris**, ainsi qu'un filtrage entreprise. Il n'existe aucun resolver public sécurisé fourni par défaut ; sans resolver, l'API refuse l'accès.

Les endpoints sont montés sous \`/api/comptabilite/\` si l'application hôte inclut \`comptabilite_ohada.urls\`. Listes d'entreprises, comptes, journaux, exercices, configurations et immobilisations : lecture uniquement. Création, validation et contrepassation d'écritures : service de domaine contrôlé. La configuration, les comptes et les immobilisations ne sont pas modifiables directement par l'ancien CRUD.

## Intégrations d'applications métiers

**Les signaux automatiques \`django-comptes\` sont supprimés** : un encaissement n'est pas nécessairement une vente et un transfert n'est pas un produit. Forcer l'ancienne option \`COMPTES_INTEGRATION_ENABLED=True\` provoque une erreur explicite. Les intégrations SahelTech utilisent ultérieurement des événements métier versionnés, qualifiés et idempotents depuis le service autonome.

## Migrations

Les migrations \`0004\` et \`0005\` ajoutent l'isolation aux ressources auxiliaires et protègent les relations historiques contre une suppression en cascade. Elles n'effectuent **aucune réattribution automatique** des anciennes lignes \`entreprise_id=""\`.

Après sauvegarde et restauration dans un environnement de recette :

\`\`\`bash
python manage.py migrate comptabilite_ohada
python manage.py audit_tenant_isolation --fail-on-anomaly
\`\`\`

La commande est en lecture seule et révèle les lignes sans entreprise, les références entre sociétés et les doublons de configuration. Les anomalies doivent être résolues par une procédure humaine traçable et un rapprochement comptable. Ne jamais exécuter une migration directement en production avant cette recette.

## Contrôles de recette avant fusion

\`\`\`bash
pip install -e '.[rest]'
python -m compileall -q comptabilite_ohada
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test comptabilite_ohada.tests
\`\`\`

Lancer ces commandes dans un hôte Django 5.2 avec PostgreSQL. Les tests doivent vérifier les deux tenants, validations, écritures équilibrées, contrepassations, autorisations, historiques et API. **Aucun résultat de tests exécutés ou de migration de production n'est attesté par cette branche.**

Voir [docs/TENANT_EXTRACTION_P0.md](docs/TENANT_EXTRACTION_P0.md) et [AGENTS.md](AGENTS.md).
