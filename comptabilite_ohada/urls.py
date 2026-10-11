"""Only tenant-verified DRF routes may be mounted.

Historic Django HTML endpoints operated without company scoping and are
unregistered until the host supplies a security-reviewed implementation.
"""
from django.conf import settings
from django.urls import include, path

app_name = "comptabilite"

urlpatterns = []
if getattr(settings, "COMPTABILITE_OHADA", {}).get("API_ENABLED", False):
    urlpatterns.append(path("", include("comptabilite_ohada.api.urls")))
