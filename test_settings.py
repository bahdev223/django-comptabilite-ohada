SECRET_KEY = 'test-only-not-for-production'
INSTALLED_APPS = ['django.contrib.auth', 'django.contrib.contenttypes', 'rest_framework', 'comptabilite_ohada']
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
USE_TZ = True
ROOT_URLCONF = 'comptabilite_ohada.api.urls'
ALLOWED_HOSTS = ['testserver']

# Test database only. Never point this harness at an existing production DB.
import os
if os.getenv('OHADA_TEST_POSTGRES') == '1':
    DATABASES = {'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('POSTGRES_DB', 'ohada_validation'),
        'USER': os.getenv('POSTGRES_USER', 'accounting_test'),
        'PASSWORD': os.getenv('POSTGRES_PASSWORD', ''),
        'HOST': os.getenv('POSTGRES_HOST', '127.0.0.1'),
        'PORT': os.getenv('POSTGRES_PORT', '5432'),
    }}
