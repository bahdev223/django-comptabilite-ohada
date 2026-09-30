from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from comptabilite_ohada.models import (
    AccesEntrepriseComptable,
    OrganisationComptable,
)
from comptabilite_ohada.tenant import resolve_entreprise_id


class TenantResolutionTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username="tenant-user", password="x")
        self.a = OrganisationComptable.objects.create(code="ENT-A", nom="Entreprise A")
        self.b = OrganisationComptable.objects.create(code="ENT-B", nom="Entreprise B")

    def _request(self, header=None):
        extra = {}
        if header:
            extra["HTTP_X_ENTERPRISE_ID"] = header
        request = self.factory.get("/", **extra)
        request.user = self.user
        return request

    def test_une_seule_entreprise_est_resolue_automatiquement(self):
        AccesEntrepriseComptable.objects.create(
            user=self.user, entreprise=self.a, role="COMPTABLE"
        )
        self.assertEqual(resolve_entreprise_id(self._request()), "ENT-A")

    def test_plusieurs_entreprises_exigent_un_header(self):
        AccesEntrepriseComptable.objects.create(
            user=self.user, entreprise=self.a, role="COMPTABLE"
        )
        AccesEntrepriseComptable.objects.create(
            user=self.user, entreprise=self.b, role="LECTURE"
        )

        from rest_framework.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            resolve_entreprise_id(self._request())

        self.assertEqual(
            resolve_entreprise_id(self._request("ENT-B")),
            "ENT-B",
        )

    def test_header_non_autorise_est_refuse(self):
        AccesEntrepriseComptable.objects.create(
            user=self.user, entreprise=self.a, role="COMPTABLE"
        )

        from rest_framework.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            resolve_entreprise_id(self._request("ENT-B"))
