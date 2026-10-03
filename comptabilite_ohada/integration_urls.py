"""Only the authenticated service-to-service accounting routes."""

from django.urls import path

from .api.integration_views import integration_costs, integration_events

urlpatterns = [
    path("api/v1/events/", integration_events, name="integration_events"),
    path("api/v1/analytics/costs/", integration_costs, name="integration_costs"),
]
