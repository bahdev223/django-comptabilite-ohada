"""Optional narrow host reusing the canonical accounting API and M2M auth."""

from django.urls import path

from .api.views import EvenementMetierViewSet, analytic_costs_view

urlpatterns = [
    path("api/v1/events/", EvenementMetierViewSet.as_view({"post": "create"}), name="integration_events"),
    path("api/v1/analytics/costs/", analytic_costs_view, name="integration_costs"),
]
