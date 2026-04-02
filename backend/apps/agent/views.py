"""Vistas de la app agent: health check y diagnóstico."""
from __future__ import annotations

import os

from django.conf import settings
from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.articles.models import Article

# Bypass proxy para Ollama (mismo hack que en services.py)
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1,0.0.0.0")


class HealthView(APIView):
    """
    Endpoint de salud del sistema.
    Devuelve el estado de Ollama, la BD y estadísticas básicas.
    """

    @extend_schema(
        summary="Health check",
        description="Verifica conectividad con BD, LLM provider y devuelve estadísticas.",
        responses={200: dict},
    )
    def get(self, request: Request) -> Response:
        result: dict = {
            "database": {"ok": False},
            "llm": {"ok": False, "provider": "unknown"},
            "stats": {"total_articles": 0, "ai_processed": 0},
        }

        # BD
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            result["database"]["ok"] = True
            result["stats"]["total_articles"] = Article.objects.count()
            result["stats"]["ai_processed"] = Article.objects.filter(ai_processed=True).count()
        except Exception as exc:
            result["database"]["error"] = str(exc)

        # LLM Provider (Ollama u OpenRouter según configuración)
        provider = getattr(settings, "LLM_PROVIDER", "ollama")
        result["llm"]["provider"] = provider

        try:
            if provider == "openrouter":
                # Verificar OpenRouter API
                api_key = getattr(settings, "OPENROUTER_API_KEY", "")
                if not api_key:
                    result["llm"]["error"] = "OPENROUTER_API_KEY not configured"
                else:
                    result["llm"]["ok"] = True
                    result["llm"]["message"] = "OpenRouter API is ready"
            else:
                # Verificar Ollama (por defecto) — lazy import
                try:
                    import ollama
                    base_url = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
                    model = getattr(settings, "OLLAMA_MODEL", "llama3.2")
                    client = ollama.Client(host=base_url, timeout=10.0)
                    models = client.list()
                    model_names = [m.get("name", m.get("model", "")) for m in models.get("models", [])]
                    result["llm"]["ok"] = True
                    result["llm"]["model"] = model
                    result["llm"]["available_models"] = model_names
                    result["llm"]["model_loaded"] = model in model_names
                except ImportError:
                    result["llm"]["error"] = "ollama not installed (production mode)"
                except Exception as exc:
                    result["llm"]["error"] = str(exc)
        except Exception as exc:
            result["llm"]["error"] = str(exc)

        overall_ok = result["database"]["ok"] and result["llm"]["ok"]
        http_status = status.HTTP_200_OK if overall_ok else status.HTTP_503_SERVICE_UNAVAILABLE
        return Response(result, status=http_status)
