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
    Endpoint de salud LIGERO del sistema (para probes y balanceadores).
    
    Solo verifica conectividad crítica sin queries costosas.
    Responde 200 si todo está operativo, 503 si hay un problema crítico.
    
    Las estadísticas detalladas están en /api/diagnostics/
    """

    @extend_schema(
        summary="Health check ligero",
        description="Verifica BD y LLM provider. Sin queries costosas.",
        responses={200: dict, 503: dict},
    )
    def get(self, request: Request) -> Response:
        result: dict = {
            "database": {"ok": False},
            "llm": {"ok": False, "provider": "unknown", "configured": False},
            "status": "down",
        }

        # BD: verificar conectividad crítica sin queries pesadas
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            result["database"]["ok"] = True
        except Exception as exc:
            result["database"]["ok"] = False
            result["database"]["error"] = str(exc)

        # LLM Provider: diferenciar "configured" (existe key/config) de "ok" (reachable)
        provider = getattr(settings, "LLM_PROVIDER", "ollama")
        result["llm"]["provider"] = provider

        if provider == "openrouter":
            api_key = getattr(settings, "OPENROUTER_API_KEY", "")
            result["llm"]["configured"] = bool(api_key)
            if not api_key:
                result["llm"]["error"] = "OPENROUTER_API_KEY not configured"
            else:
                # Verificar reachability: intento liviano sin llamada al modelo
                try:
                    import httpx
                    with httpx.Client(timeout=5.0) as client:
                        # GET /models es rápido y no requiere balance de tokens
                        resp = client.get(
                            "https://openrouter.ai/api/v1/models",
                            headers={"Authorization": f"Bearer {api_key}"},
                        )
                        if resp.status_code == 401:
                            result["llm"]["error"] = "OpenRouter API key invalid (401)"
                        elif resp.status_code == 200:
                            result["llm"]["ok"] = True
                        else:
                            result["llm"]["error"] = f"OpenRouter HTTP {resp.status_code}"
                except Exception as exc:
                    result["llm"]["error"] = f"OpenRouter unreachable: {str(exc)[:100]}"
        else:
            # Ollama (por defecto)
            try:
                import ollama
                base_url = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
                model = getattr(settings, "OLLAMA_MODEL", "llama3.2")
                result["llm"]["configured"] = True
                client = ollama.Client(host=base_url, timeout=5.0)
                # Verificación liviana: list models sin generar respuestas
                models = client.list()
                model_names = [m.get("name", m.get("model", "")) for m in models.get("models", [])]
                result["llm"]["ok"] = True
                result["llm"]["available_models"] = len(model_names)
                result["llm"]["model_loaded"] = model in model_names
            except ImportError:
                result["llm"]["configured"] = False
                result["llm"]["error"] = "ollama not installed (production mode)"
            except Exception as exc:
                result["llm"]["configured"] = True
                result["llm"]["error"] = str(exc)[:100]

        # Estado general
        overall_ok = result["database"]["ok"] and result["llm"]["ok"]
        result["status"] = "up" if overall_ok else "down"
        
        http_status = status.HTTP_200_OK if overall_ok else status.HTTP_503_SERVICE_UNAVAILABLE
        return Response(result, status=http_status)


class DiagnosticsView(APIView):
    """
    Endpoint de diagnóstico PESADO: estadísticas, conteos, detalles operativos.
    
    Este endpoint puede ser más costoso en queries porque no se espera que
    sea llamado constantemente por balanceadores o probes, sino por dashboards
    de admin o debugging manual.
    """

    @extend_schema(
        summary="Diagnóstico del sistema",
        description="Estadísticas detalladas, conteos de artículos, modelos disponibles.",
        responses={200: dict},
    )
    def get(self, request: Request) -> Response:
        result: dict = {
            "database": {"ok": False},
            "llm": {"ok": False, "provider": "unknown"},
            "stats": {"total_articles": 0, "ai_processed": 0, "ai_processing": 0, "ai_failed": 0},
        }

        # BD: stats detalladas
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            result["database"]["ok"] = True
            result["stats"]["total_articles"] = Article.objects.count()
            result["stats"]["ai_processed"] = Article.objects.filter(ai_processed=True).count()
            result["stats"]["ai_processing"] = Article.objects.filter(ai_processing=True).count()
            result["stats"]["ai_failed"] = Article.objects.filter(ai_error__isnull=False).exclude(ai_error="").count()
        except Exception as exc:
            result["database"]["error"] = str(exc)

        # LLM Provider details
        provider = getattr(settings, "LLM_PROVIDER", "ollama")
        result["llm"]["provider"] = provider

        try:
            if provider == "openrouter":
                api_key = getattr(settings, "OPENROUTER_API_KEY", "")
                result["llm"]["api_key_configured"] = bool(api_key)
                result["llm"]["model"] = getattr(settings, "OPENROUTER_MODEL", "qwen/qwen3.6-plus:free")
                premium = getattr(settings, "OPENROUTER_MODEL_PREMIUM", "")
                if premium:
                    result["llm"]["premium_model"] = premium
                if api_key:
                    result["llm"]["ok"] = True
                    result["llm"]["message"] = "OpenRouter API is configured and ready"
            else:
                # Ollama details
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

        return Response(result, status=status.HTTP_200_OK)


class ProbeModelView(APIView):
    """
    Endpoint para detectar el modelo OpenRouter disponible en tiempo real.
    GET /api/probe-model/ -> {"model": "...", "cached": bool, "source": "probe|cache"}
    Util para que el frontend sepa qué modelo está activo al cargar la pagina.
    """

    @extend_schema(
        summary="Probe modelo OpenRouter disponible",
        description="Detecta y cachea el primer modelo disponible (sin 429). TTL 5min.",
        responses={200: dict, 503: dict},
    )
    def get(self, request: Request) -> Response:
        from django.core.cache import cache
        from apps.agent.openrouter_service import OpenRouterService, _PROBE_CACHE_KEY

        provider = getattr(settings, "LLM_PROVIDER", "ollama")
        if provider != "openrouter":
            return Response(
                {"error": "LLM_PROVIDER no es openrouter", "provider": provider},
                status=status.HTTP_400_BAD_REQUEST,
            )

        api_key = getattr(settings, "OPENROUTER_API_KEY", "")
        if not api_key:
            return Response(
                {"error": "OPENROUTER_API_KEY no configurada"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        force = request.query_params.get("force", "false").lower() == "true"

        # Verificar cache primero (sin hacer probe)
        if not force:
            cached_model = cache.get(_PROBE_CACHE_KEY)
            if cached_model:
                return Response({
                    "model": cached_model,
                    "cached": True,
                    "source": "cache",
                })

        # Hacer probe en tiempo real
        try:
            service = OpenRouterService()
            model = service.probe_available_model(force=True)
            return Response({
                "model": model,
                "cached": False,
                "source": "probe",
            })
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


