"""URLs principales del proyecto — Agente Escribano."""
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import RedirectView, TemplateView
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

urlpatterns = [
    # 1. Admin y API (Rutas prioritarias)
    path("admin/", admin.site.urls),

    # Las apps definen sus propios prefijos internamente:
    # articles → articles/, notebooks/, jobs/
    # search   → search/
    # agent    → health/, diagnostics/
    path("api/", include("apps.articles.urls")),
    path("api/", include("apps.search.urls")),
    path("api/", include("apps.agent.urls")),

    # OpenAPI / Swagger (dentro del espacio /api/)
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),

    # 2. CATCH-ALL para React Router (SPA)
    # Cualquier ruta que NO comience por api/, admin/, static/ o media/ 
    # se delega al frontend (index.html), permitiendo el routing en el navegador.
    re_path(r"^(?!api/|admin/|static/|media/).*$", TemplateView.as_view(template_name="index.html"), name="frontend_spa"),

    # Raíz → Redirige a la documentación de la API como fallback
    path("", RedirectView.as_view(url="/api/docs/", permanent=False)),
]
