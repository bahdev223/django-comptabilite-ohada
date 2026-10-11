from django.test import TestCase
from comptabilite_ohada.tenancy import tenant_scope


class TenantTestCase(TestCase):
    """Run older single-company tests in a trusted explicit tenant context."""

    def run(self, result=None):
        with tenant_scope("legacy-single-company-tests"):
            return super().run(result)
