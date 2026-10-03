"""Narrow authenticated HTTP surface for project accounting integration."""

import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from ..services.project_integration import (
    IntegrationError,
    analytic_costs,
    record_event,
    tenant_for_key,
)


@csrf_exempt
def integration_events(request):
    if request.method != "POST":
        return JsonResponse({"detail": "Méthode non autorisée."}, status=405)
    try:
        tenant = tenant_for_key(request.headers.get("X-API-Key"))
        if request.content_type != "application/json":
            raise IntegrationError("JSON requis.", 415)
        try:
            payload = json.loads(request.body)
        except (ValueError, UnicodeDecodeError) as exc:
            raise IntegrationError("JSON invalide.") from exc
        entry, created = record_event(tenant, payload)
        return JsonResponse({"entry_id": entry.pk, "status": "recorded"}, status=201 if created else 200)
    except IntegrationError as exc:
        return JsonResponse({"detail": str(exc)}, status=exc.status)


def integration_costs(request):
    if request.method != "GET":
        return JsonResponse({"detail": "Méthode non autorisée."}, status=405)
    try:
        tenant = tenant_for_key(request.headers.get("X-API-Key"))
        return JsonResponse(analytic_costs(tenant, request.GET.dict()))
    except IntegrationError as exc:
        return JsonResponse({"detail": str(exc)}, status=exc.status)
