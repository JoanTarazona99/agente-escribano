"""URLs principales del proyecto — Agente Escribano."""
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

urlpatterns = [
    # Raíz → redirige a la documentación de la API
    path("", RedirectView.as_view(url="/api/docs/", permanent=False)),

    # Admin
    path("admin/", admin.site.urls),

    # API v1
    path("api/", include("apps.search.urls")),
    path("api/", include("apps.articles.urls")),
    path("api/", include("apps.agent.urls")),

    # OpenAPI / Swagger
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]
