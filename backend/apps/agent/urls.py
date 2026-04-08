"""URLs de la app agent — health check y diagnóstico."""
from django.urls import path

from .views import HealthView, DiagnosticsView, ProbeModelView

urlpatterns = [
    path("health/", HealthView.as_view(), name="health-check"),
    path("diagnostics/", DiagnosticsView.as_view(), name="diagnostics"),
    path("probe-model/", ProbeModelView.as_view(), name="probe-model"),
]

