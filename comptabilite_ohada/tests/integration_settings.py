"""Loopback-only settings for the disposable two-service integration test."""

import json
import os

SECRET_KEY = "local-accounting-integration-test-only"
DEBUG = True
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
ROOT_URLCONF = "comptabilite_ohada.integration_urls"
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "rest_framework",
    "django_filters",
    "comptabilite_ohada",
]
MIDDLEWARE = []
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("ACCOUNTING_TEST_PG_DB", "accounting_it"),
        "USER": os.environ.get("ACCOUNTING_TEST_PG_USER", "integration_test"),
        "HOST": "127.0.0.1",
        "PORT": os.environ.get("ACCOUNTING_TEST_PG_PORT", "55432"),
    }
}
COMPTABILITE_OHADA = {
    "DEVISE_PAR_DEFAUT": "XOF",
    "API_ENABLED": True,
    "COMPTES_INTEGRATION_ENABLED": False,
    "INTEGRATION_KEYS": json.loads(os.environ.get("ACCOUNTING_TEST_TENANT_KEYS", "{}")),
}
