from dataclasses import dataclass

from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import ApplicationClienteComptable


@dataclass
class APIClientPrincipal:
    application: ApplicationClienteComptable

    @property
    def is_authenticated(self):
        return True

    @property
    def is_superuser(self):
        return False

    @property
    def is_staff(self):
        return False

    @property
    def is_api_client(self):
        return True

    @property
    def entreprise_id(self):
        return self.application.entreprise.code

    @property
    def api_scopes(self):
        return set(self.application.scopes or [])

    @property
    def username(self):
        return f"api:{self.application.nom}"

    @property
    def pk(self):
        return None

    def __str__(self):
        return self.username


class AccountingAPIKeyAuthentication(BaseAuthentication):
    """Authentifie les intégrations via X-API-Key ou Authorization: ApiKey."""

    keyword = "ApiKey"

    def authenticate(self, request):
        raw = request.headers.get("X-API-Key", "").strip()

        if not raw:
            authorization = request.headers.get("Authorization", "")
            if authorization.startswith(self.keyword + " "):
                raw = authorization[len(self.keyword) + 1 :].strip()

        if not raw:
            return None

        prefixe = raw[:16]
        application = ApplicationClienteComptable.objects.select_related(
            "entreprise"
        ).filter(
            prefixe=prefixe,
            actif=True,
            entreprise__actif=True,
        ).first()

        if application is None or not application.verifier_secret(raw):
            raise AuthenticationFailed("Clé API comptable invalide.")

        ApplicationClienteComptable.objects.filter(pk=application.pk).update(
            last_used_at=timezone.now()
        )
        return APIClientPrincipal(application), application
