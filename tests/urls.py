from django.urls import include, path

urlpatterns = [
    path("", include("comptabilite_ohada.urls")),
]
