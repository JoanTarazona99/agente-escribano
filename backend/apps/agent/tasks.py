"""Tareas ejecutables por django-q2 para el agente IA."""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import httpx

from django.conf import settings

logger = logging.getLogger(__name__)


def get_models_file_path():
    """Ruta al archivo JSON de modelos gratuitos."""
    return Path(settings.BASE_DIR).parent / "config" / "llm_models.json"


def refresh_openrouter_free_models():
    """
    Función ejecutable por django-q2 (vía management command).
    Verifica modelos gratuitos en OpenRouter y actualiza config/llm_models.json.
    
    Se ejecuta diariamente a las 02:00 UTC (05:00 MSK).
    
    Lógica:
    1. Obtiene lista de modelos desde OpenRouter API
    2. Filtra por pricing.prompt == "0" AND pricing.completion == "0"
    3. Valida sufijo :free para legibilidad (pero acepta modelos sin sufijo si son gratis)
    4. Prioriza modelos conocidos y de desempeño observado
    5. Deduplica y guarda top 5 en config/llm_models.json
    """
    try:
        api_key = settings.OPENROUTER_API_KEY
        if not api_key:
            logger.warning("⚠️ OPENROUTER_API_KEY no configurada. Saltando refresh de modelos.")
            return

        logger.info("🔄 [TASK] Verificando modelos gratuitos en OpenRouter...")

        # Obtener lista de modelos desde OpenRouter
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()

        # Validación defensiva: filtrar modelos con pricing cero
        free_models = []
        for m in data.get("data", []):
            model_id = m.get("id", "")
            pricing = m.get("pricing", {})
            
            # Requisitos:
            # 1. pricing.prompt == "0" (gratis)
            # 2. pricing.completion == "0" (gratis)
            # 3. Preferencia: ID contiene :free para legibilidad
            prompt_free = pricing.get("prompt") == "0"
            completion_free = pricing.get("completion") == "0"
            
            if prompt_free and completion_free:
                free_models.append(model_id)
                if ":free" not in model_id:
                    logger.debug(
                        "⚠️ Modelo gratuito sin sufijo :free: %s (pero es gratis)",
                        model_id,
                    )

        logger.info(
            "✅ [TASK] Encontrados %d modelos gratuitos en OpenRouter",
            len(free_models),
        )

        if not free_models:
            logger.warning("⚠️ [TASK] No se encontraron modelos gratuitos. Manteniendo lista anterior.")
            return

        # Priorizar modelos conocidos por desempeño observado
        priority_order = [
            "qwen/qwen3.6-plus:free",
            "qwen/qwen2.5-72b-instruct:free",
            "deepseek/deepseek-r1:free",
            "meta-llama/llama-3.3-70b-instruct:free",
            "google/gemma-3-27b-it:free",
            "nvidia/nemotron-3-super-120b-a12b:free",
        ]

        # Ordenar: primero los prioritarios, luego el resto (deduplicar)
        prioritized = [m for m in priority_order if m in free_models]
        rest = [m for m in free_models if m not in priority_order]
        ordered_models = prioritized + rest
        
        # Deduplicar por si OpenRouter devuelve variantes repetidas
        selected_models = []
        seen = set()
        for model in ordered_models[:5]:  # max 5 modelos
            if model not in seen:
                selected_models.append(model)
                seen.add(model)

        logger.info(
            "📋 [TASK] Modelo prioritario: %s. Fallbacks: %s",
            selected_models[0] if selected_models else "NINGUNO",
            ", ".join(selected_models[1:]),
        )

        # Guardar en archivo JSON
        file_path = get_models_file_path()
        file_path.parent.mkdir(parents=True, exist_ok=True)

        config = {
            "openrouter_free_models": selected_models,
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "count": len(selected_models),
            "note": "Actualizado automáticamente diariamente a las 02:00 UTC por django-q2",
        }

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        logger.info(
            "✅ [TASK] Config guardada. Modelos: %s en %s",
            len(selected_models), file_path,
        )

    except httpx.HTTPStatusError as e:
        logger.error(
            "❌ [TASK] Error HTTP al verificar OpenRouter: %d %s",
            e.response.status_code, e.response.text[:200],
        )
    except httpx.RequestError as e:
        logger.error("❌ [TASK] Error de conexión a OpenRouter: %s", e)
    except Exception as e:
        logger.error(
            "❌ [TASK] Error inesperado al actualizar modelos: %s",
            e, exc_info=True,
        )
