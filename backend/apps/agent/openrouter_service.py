"""
OpenRouter LLM Service para produccion.
Alternativa a Ollama cuando se despliega en Render con plan gratuito.

API: https://openrouter.ai/api/v1
Documentacion: https://openrouter.ai/docs

Optimizado: 2 llamadas API batch con mega-prompt (20s + 50s = 70s << 300s timeout).

Resilencia en free tier (basado en datos reales, Abril 2026):
  - Modelo principal: google/gemini-2.0-flash-exp:free (rápido, económico)
  - Fallbacks: step-3.5-flash → qwen3-235b → gemma-3-4b → llama-4-scout
  - Estrategia: priorizar modelos "flash" y ligeros para evitar 429
  - Nota: modelos grandes populares (gemma-27b, llama-70b) saturan el pool free
  - Retry: 2 reintentos en 429 con backoff: 1.5s, 3s, 6s
  - Premium fallback: modelo no-free opcional si configurado
  - Timeout explícito: connect=10s, read=50s, write=10s, pool=5s
  - Deadline global: 120s

Configuración (.env):
  OPENROUTER_MODEL=stepfun/step-3.5-flash:free  (defecto)
  OPENROUTER_MODEL_PREMIUM=  (opcional, ej: openai/gpt-4-turbo)
  Nota: Modelos fallback se cargan dinámicamente desde config/llm_models.json
"""
import logging
import json
import re
import time
from pathlib import Path
from typing import Optional

import httpx
from django.conf import settings
from django.core.cache import cache

from apps.articles.models import Article

logger = logging.getLogger(__name__)


# ── Excepciones tipificadas ──────────────────────────────────────────

class OpenRouterError(Exception):
    """Error base para llamadas a OpenRouter."""
    code: str = "unknown"

    def __init__(self, message: str, code: str | None = None):
        self.message = message
        if code:
            self.code = code
        super().__init__(message)


class RateLimitError(OpenRouterError):
    """Todos los modelos agotaron retries por rate-limiting (429)."""
    code = "rate_limited"


class AuthError(OpenRouterError):
    """API key inválida o expirada (401/403)."""
    code = "auth_error"


class ModelNotFoundError(OpenRouterError):
    """El modelo solicitado no existe en OpenRouter (404)."""
    code = "model_unavailable"


class NoContentError(OpenRouterError):
    """El modelo no generó contenido útil (respuesta vacía recurrente)."""
    code = "no_content"


class DeadlineExceededError(OpenRouterError):
    """Se superó el tiempo máximo total para la llamada."""
    code = "timeout"


# Campos que se actualizan al procesar un articulo.
_AI_UPDATE_FIELDS = [
    "title_es", "title_en", "title_ru",
    "abstract_es", "abstract_en", "abstract_ru",
    "ai_summary", "ai_summary_es", "ai_summary_en", "ai_summary_ru",
    "ai_analysis", "ai_analysis_es", "ai_analysis_en", "ai_analysis_ru",
    "ai_processed", "ai_processing", "ai_error", "ai_error_code",
]

# Modelos gratuitos de fallback, ordenados por velocidad y disponibilidad.
# Estrategia: priorizar modelos "flash" (rápidos, bajo consumo) sobre modelos grandes.
# Modelos grandes (gemma-27b, llama-70b) saturan el pool gratuito con 429 frecuente.
# Se actualiza diariamente por task django-q2 en config/llm_models.json
_FALLBACK_MODELS = [
    "google/gemini-2.0-flash-exp:free",                   # 1º Flash, rápido, buen pool
    "stepfun/step-3.5-flash:free",                         # 2º Muy estable (34 requests OK)
    "qwen/qwen3-235b-a22b:free",                           # 3º Qwen MoE, eficiente
    "google/gemma-3-4b-it:free",                            # 4º Modelo pequeño, rápido
    "meta-llama/llama-4-scout:free",                        # 5º Scout ligero
    "deepseek/deepseek-r1:free",                            # 6º Capaz, último recurso
]

# Reintentos en 429 antes de saltar al siguiente modelo.
# 2 reintentos = 3 intentos totales (1 original + 2 retries con backoff exponencial).
_MAX_RETRIES_PER_MODEL = 2
# Base para backoff exponencial: delay = base * 2^attempt
# Ejemplo: 1.5s, 3s, 6s. Mantenemos corto para no agravar deadline global.
_RETRY_BASE_DELAY = 1.5
# Tiempo maximo total para _call_openrouter (segundos).
# Con 2 batch calls secuenciales: batch_translate ~20s + mega-prompt ~50s = 70s,
# que deja margen frente al timeout de django-q2 (300s) para que el except
# pueda limpiar la BD antes del kill.
_CALL_DEADLINE = 120.0
# TTL del cache para el modelo disponible (segundos). Se re-prueba cada 5 min.
_PROBE_CACHE_TTL = 300
_PROBE_CACHE_KEY = "openrouter_available_model"


class OpenRouterService:
    """
    Servicio que usa OpenRouter API para analisis y resumen de articulos.
    Compatible con la misma interfaz que OllamaService.

    Pipeline: 2 llamadas JSON:
    1. Traducir titulo + abstract a ES/EN/RU         (~20s, ~1200 tokens)
    2. Generar summary + analysis EN + traducir ES/RU (~50s, ~3000 tokens)
    Total: ~70s << 300s timeout django-q2

    Resilencia:
    - Modelo principal: google/gemini-2.0-flash-exp:free (por defecto)
    - Fallbacks dinámicos: cargados desde config/llm_models.json (actualizado diariamente)
    - Estrategia: modelos flash/ligeros primero para evitar 429 de pool saturado
    - Timeout explicito: connect=10s, read=50s, write=10s, pool=5s
    - Deadline global: 120s (respeta timeout total de django-q2)
    """

    @staticmethod
    def _load_fallback_models() -> list[str]:
        """
        Carga lista de modelos gratuitos desde config/llm_models.json.
        Si el archivo no existe o está corrompido, usa la lista hardcoded.
        
        Returns:
            list[str]: Lista de model IDs ordenados por prioridad
        """
        try:
            # 1. Definir rutas potenciales (Producción Docker/Render vs Desarrollo Local)
            potential_paths = [
                Path(settings.BASE_DIR) / "llm_models.json",  # Raíz del contenedor
                Path(settings.BASE_DIR).parent / "config" / "llm_models.json",  # Local repo
                Path(settings.BASE_DIR) / "config" / "llm_models.json",  # Estructura interna
            ]
            
            config_file = None
            for path in potential_paths:
                if path.exists():
                    config_file = path
                    break
            
            if not config_file:
                logger.warning(
                    "⚠️ Archivo llm_models.json no encontrado en rutas conocidas. "
                    "Usando lista hardcoded de fallbacks."
                )
                return list(_FALLBACK_MODELS)
            
            with open(config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            models = data.get("openrouter_free_models", [])
            if not models:
                logger.warning(
                    "⚠️ Lista de modelos vacía en config/llm_models.json. "
                    "Usando fallback hardcoded."
                )
                return list(_FALLBACK_MODELS)
            
            logger.info(
                f"✅ Modelos gratuitos cargados desde JSON ({len(models)} disponibles). "
                f"Última actualización: {data.get('last_updated', 'desconocida')}"
            )
            return models
        
        except json.JSONDecodeError as e:
            logger.error(
                f"❌ Error al parsear config/llm_models.json: {e}. "
                f"Usando fallback hardcoded."
            )
            return list(_FALLBACK_MODELS)
        except Exception as e:
            logger.error(
                f"❌ Error al cargar modelos desde JSON: {e}. "
                f"Usando fallback hardcoded.",
                exc_info=True
            )
            return list(_FALLBACK_MODELS)

    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        self.base_url = "https://openrouter.ai/api/v1"
        # Modelo principal: google/gemini-2.0-flash-exp:free (rápido y económico).
        # Evitar modelos grandes populares que dan 429 constante (gemma-27b, llama-70b).
        # Premium fallback (opcional): modelo no-free si está configurado.
        self.model = getattr(
            settings, "OPENROUTER_MODEL", "google/gemini-2.0-flash-exp:free"
        )
        
        # Construir lista de fallbacks: gratuitos (cargados dinámicamente) + premium opcional
        fallback_models = self._load_fallback_models()
        premium = getattr(settings, "OPENROUTER_MODEL_PREMIUM", "")
        if premium:
            fallback_models.append(premium)
            logger.info("Modelo premium activado como último fallback: %s", premium)
        self._fallback_models = fallback_models
        
        # Timeout explicito por fase para evitar hang en lectura SSL stream.
        # connect=10s, read=50s (permite mega-prompt lento), write=10s, pool=5s.
        self.timeout = httpx.Timeout(connect=10.0, read=50.0, write=10.0, pool=5.0)

    # ================================================================
    # Probe: detectar modelo disponible en tiempo real
    # ================================================================
    def probe_available_model(self, force: bool = False) -> str:
        """
        Detecta el primer modelo de OpenRouter disponible (sin 429).
        Resultado cacheado _PROBE_CACHE_TTL segundos para evitar ping en
        cada llamada. Llamar con force=True para invalidar el cache.

        Returns:
            str: model ID del primer modelo que responde sin error.
        """
        if not force:
            cached = cache.get(_PROBE_CACHE_KEY)
            if cached:
                logger.debug("Probe cache hit: %s", cached)
                return cached

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://agente-escribano.onrender.com",
            "X-Title": "Agente Escribano - Universidad",
            "Content-Type": "application/json",
        }
        probe_timeout = httpx.Timeout(connect=8.0, read=15.0, write=5.0, pool=3.0)
        models_to_probe = [self.model] + [
            m for m in self._fallback_models if m != self.model
        ]
        logger.info(
            "Probe iniciado: verificando %d modelos en OpenRouter...",
            len(models_to_probe),
        )
        for model in models_to_probe:
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 1,
                "temperature": 0,
            }
            try:
                with httpx.Client(timeout=probe_timeout) as client:
                    resp = client.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                if resp.status_code == 429:
                    logger.debug("Probe: %s -> 429 (rate limited)", model)
                    continue
                if resp.status_code in (401, 403):
                    logger.warning("Probe: auth error %d. Abortando.", resp.status_code)
                    break
                if resp.status_code == 404:
                    logger.debug("Probe: %s -> 404 (no existe)", model)
                    continue
                if resp.status_code >= 400:
                    logger.debug("Probe: %s -> %d", model, resp.status_code)
                    continue
                # 2xx -> modelo disponible
                logger.info("Probe OK: modelo disponible -> %s", model)
                cache.set(_PROBE_CACHE_KEY, model, timeout=_PROBE_CACHE_TTL)
                if model != self.model:
                    logger.info(
                        "Probe: actualizando self.model %s -> %s",
                        self.model,
                        model,
                    )
                    self.model = model
                return model
            except httpx.TimeoutException:
                logger.debug("Probe: %s -> timeout", model)
                continue
            except Exception as e:
                logger.debug("Probe: %s -> error: %s", model, e)
                continue

        # Ninguno disponible: usar el modelo configurado por defecto
        logger.warning(
            "Probe: todos los modelos no disponibles. Usando configurado: %s",
            self.model,
        )
        return self.model

    # ================================================================
    # Punto de entrada principal
    # ================================================================

    def process_article(self, article: Article) -> dict:
        """
        Procesa un articulo con 3 llamadas batch:
        Paso 1: traducir titulo + abstract a ES/EN/RU
        Paso 2: generar resumen + analisis en EN
        Paso 3: traducir resumen + analisis a ES/RU

        Args:
            article: Instancia de Article

        Returns:
            dict con claves actualizadas
        """
        if not self.api_key:
            logger.warning("OPENROUTER_API_KEY no configurada. Saltando analisis.")
            return {}
                  # Detectar modelo disponible antes de procesar (cache 5min)
        self.probe_available_model()

        result: dict = {}
        lang = article.language_original or "en"
        # Para archivos subidos, usar full_text como fuente principal
        full_text = getattr(article, "full_text", "") or ""

        try:
            # -- Paso 1: traducir titulo + abstract a ES/EN/RU (1 llamada) --
            text_for_translation = full_text[:3000] if full_text else article.abstract_original
            need_tr = (
                (article.title and any(
                    not getattr(article, f"title_{l}")
                    for l in ("es", "en", "ru") if l != lang
                ))
                or (text_for_translation and any(
                    not getattr(article, f"abstract_{l}")
                    for l in ("es", "en", "ru") if l != lang
                ))
            )
            if need_tr:
                tr = self._batch_translate(
                    article.title, text_for_translation or article.abstract_original, lang,
                )
                for key in (
                    "title_es", "title_en", "title_ru",
                    "abstract_es", "abstract_en", "abstract_ru",
                ):
                    val = tr.get(key)
                    if val and not getattr(article, key):
                        setattr(article, key, val)
                        result[key] = val

            # -- Paso 2: generar resumen + analisis EN (1 llamada) --
            best_abstract = (
                full_text[:4000] if full_text
                else article.abstract_en
                or article.abstract_original
                or ""
            )
            authors = article.authors[:200] if article.authors else "Unknown"
            keywords = getattr(article, "keywords", "") or ""
            journal = getattr(article, "journal", "") or ""

            need_sa = (
                not article.ai_summary
                or not article.ai_analysis
                or not article.ai_summary_es
                or not article.ai_summary_ru
                or not article.ai_analysis_es
                or not article.ai_analysis_ru
            )
            if need_sa:
                sa = self._generate_and_translate_sa(
                    article.title, best_abstract, authors,
                    keywords=keywords, journal=journal,
                )
                sa_field_map = {
                    "summary_en": ("ai_summary", "ai_summary_en"),
                    "summary_es": ("ai_summary_es",),
                    "summary_ru": ("ai_summary_ru",),
                    "analysis_en": ("ai_analysis", "ai_analysis_en"),
                    "analysis_es": ("ai_analysis_es",),
                    "analysis_ru": ("ai_analysis_ru",),
                }
                for src_key, dest_fields in sa_field_map.items():
                    val = sa.get(src_key)
                    if val:
                        for dest in dest_fields:
                            if not getattr(article, dest):
                                setattr(article, dest, val)
                                result[dest] = val

            if not result:
                logger.error(
                    "Articulo %s: OpenRouter no genero contenido. "
                    "Modelo: %s. Verifica OPENROUTER_API_KEY y que el "
                    "modelo exista en https://openrouter.ai/models",
                    article.id, self.model,
                )
                raise NoContentError(
                    f"OpenRouter no genero contenido para articulo {article.id}. "
                    f"El modelo '{self.model}' puede no estar disponible. "
                    f"Consulta https://openrouter.ai/models"
                )

            article.ai_processed = True
            article.save(update_fields=_AI_UPDATE_FIELDS)
            logger.info(
                "Articulo %s procesado con OpenRouter (modelo: %s, "
                "campos: %s)",
                article.id, self.model, list(result.keys()),
            )
            return result

        except Exception as e:
            logger.error(
                "Error fatal procesando articulo %s con OpenRouter: %s",
                article.id, e,
            )
            # Resetear ai_processing y guardar error + progreso parcial.
            # Usar update() atomico (1 SQL) por si SIGALRM interrumpe.
            error_code = getattr(e, "code", "unknown")
            partial = {}
            for f in _AI_UPDATE_FIELDS:
                val = getattr(article, f, None)
                if val and f not in ("ai_processed", "ai_processing", "ai_error", "ai_error_code"):
                    partial[f] = val
            partial.update(
                ai_processing=False,
                ai_error=str(e)[:500],
                ai_error_code=error_code,
            )
            try:
                Article.objects.filter(pk=article.pk).update(**partial)
            except Exception:
                pass
            raise

    # ================================================================
    # Batch methods
    # ================================================================

    def _batch_translate(
        self, title: str, abstract: str, source_lang: str,
    ) -> dict:
        """Traduce titulo + abstract a ES/EN/RU en 1 llamada -> JSON."""
        targets = [l for l in ("es", "en", "ru") if l != source_lang]
        lang_names = {"es": "Spanish", "en": "English", "ru": "Russian"}

        keys: list[str] = []
        if title:
            keys += [f"title_{l}" for l in targets]
        if abstract:
            keys += [f"abstract_{l}" for l in targets]
        if not keys:
            return {}

        schema_parts = ", ".join(
            f'"{k}": "<translation to {lang_names[k.split("_")[-1]]}>"'
            for k in keys
        )
        prompt = (
            "Translate the following academic text. "
            "Return ONLY a valid JSON object with these keys:\n"
            f"{{{schema_parts}}}\n\n"
            f"TITLE: {title or '(none)'}\n\n"
            f"ABSTRACT: {abstract or '(none)'}\n\n"
            "Rules:\n"
            "- Preserve LaTeX/math ($...$) exactly\n"
            "- Keep proper nouns, chemical formulas, abbreviations\n"
            "- Return ONLY the JSON, no markdown, no explanation"
        )

        data = self._call_openrouter_json(prompt, max_tokens=1200)
        if data:
            return data

        # Fallback: traducciones individuales
        logger.info("Batch translate fallo, usando fallback individual")
        result: dict = {}
        if title:
            for l in targets:
                result[f"title_{l}"] = self._translate(title, l)
        if abstract:
            for l in targets:
                result[f"abstract_{l}"] = self._translate(abstract, l)
        return result

    def _generate_and_translate_sa(
        self, title: str, abstract: str, authors: str,
        keywords: str = "", journal: str = "",
    ) -> dict:
        """
        Mega-prompt: genera resumen + analisis en EN y traduce a ES/RU,
        todo en 1 sola llamada API -> JSON con 6 claves.

        Si no hay abstract, usa título + keywords + journal para generar
        un resumen fiel sin alucinaciones.

        Fallback: si el JSON falla, degrada a 2 llamadas separadas
        (_generate_summary_and_analysis + _batch_translate_sa).

        Returns:
            dict con claves: summary_en, summary_es, summary_ru,
                             analysis_en, analysis_es, analysis_ru.
        """
        has_abstract = abstract and abstract.strip()

        if not has_abstract and not title.strip():
            return {}

        if has_abstract:
            prompt = (
                "Analyze this scientific article. Return ONLY a valid JSON "
                "object with these 6 keys:\n\n"
                '{"summary_en": "Concise summary in English (150-250 words) '
                "covering: objectives, methodology, key findings, conclusions, "
                "and relevance to water dissociation/recombination in "
                'electromembrane systems.",\n'
                '"summary_es": "Same summary translated to Spanish.",\n'
                '"summary_ru": "Same summary translated to Russian.",\n'
                '"analysis_en": "Structured analysis in English (200-350 words) '
                "with sections: 1. TYPE (theoretical/experimental/review/mixed), "
                "2. METHODOLOGY, 3. KEY FINDINGS (2-3 bullet points), "
                '4. EMS RELEVANCE, 5. LIMITATIONS, 6. RATING N/10.",\n'
                '"analysis_es": "Same analysis translated to Spanish.",\n'
                '"analysis_ru": "Same analysis translated to Russian."}\n\n'
                f"Title: {title}\nAuthors: {authors}\nAbstract: {abstract}\n\n"
                "Rules:\n"
                "- Preserve LaTeX/math ($...$), chemical formulas, abbreviations\n"
                "- Keep numbered sections and bullet points in all languages\n"
                "- Return ONLY the JSON. No markdown code blocks. No extra text."
            )
        else:
            # Prompt especial para artículos sin abstract (ej: WOS Starter API)
            kw_info = f"Keywords: {keywords}\n" if keywords else ""
            j_info = f"Journal: {journal}\n" if journal else ""
            prompt = (
                "This article has NO abstract available. Based ONLY on the title, "
                "keywords, and journal below, generate a FAITHFUL summary and analysis.\n\n"
                "IMPORTANT: Do NOT invent specific results or methodology. "
                "Use hedging language like 'likely', 'presumably', 'appears to focus on'.\n\n"
                "Return ONLY a valid JSON object with these 6 keys:\n\n"
                '{"summary_en": "Brief metadata-based summary in English (80-120 words) '
                "describing the likely research topic, field, and potential relevance "
                'to water dissociation/recombination in electromembrane systems.",\n'
                '"summary_es": "Same summary translated to Spanish.",\n'
                '"summary_ru": "Same summary translated to Russian.",\n'
                '"analysis_en": "Brief metadata-based analysis in English (100-200 words) '
                "with sections: 1. LIKELY TYPE, 2. PROBABLE FIELD, "
                "3. POTENTIAL RELEVANCE TO EMS, 4. NOTE: Analysis based on metadata only "
                '(no abstract available). RATING N/10 (metadata-based).",\n'
                '"analysis_es": "Same analysis translated to Spanish.",\n'
                '"analysis_ru": "Same analysis translated to Russian."}\n\n'
                f"Title: {title}\nAuthors: {authors}\n{kw_info}{j_info}\n"
                "Rules:\n"
                "- Be honest about the limited information available\n"
                "- Preserve LaTeX/math, chemical formulas, abbreviations\n"
                "- Return ONLY the JSON. No markdown code blocks. No extra text."
            )

        data = self._call_openrouter_json(prompt, max_tokens=4000)
        if data and any(
            data.get(k) for k in (
                "summary_en", "summary_es", "summary_ru",
                "analysis_en", "analysis_es", "analysis_ru",
            )
        ):
            logger.info("Mega-prompt SA exitoso (6 claves)")
            return data

        # Fallback: 2 llamadas separadas (generar EN + traducir ES/RU)
        logger.info("Mega-prompt SA fallo, degradando a 2 llamadas separadas")
        result: dict = {}
        sa = self._generate_summary_and_analysis(title, abstract, authors)
        if sa.get("summary"):
            result["summary_en"] = sa["summary"]
        if sa.get("analysis"):
            result["analysis_en"] = sa["analysis"]

        summary_en = result.get("summary_en", "")
        analysis_en = result.get("analysis_en", "")
        if summary_en or analysis_en:
            sa_tr = self._batch_translate_sa(summary_en, analysis_en)
            if sa_tr.get("ai_summary_es"):
                result["summary_es"] = sa_tr["ai_summary_es"]
            if sa_tr.get("ai_summary_ru"):
                result["summary_ru"] = sa_tr["ai_summary_ru"]
            if sa_tr.get("ai_analysis_es"):
                result["analysis_es"] = sa_tr["ai_analysis_es"]
            if sa_tr.get("ai_analysis_ru"):
                result["analysis_ru"] = sa_tr["ai_analysis_ru"]

        return result

    def _generate_summary_and_analysis(
        self, title: str, abstract: str, authors: str,
    ) -> dict:
        """Genera resumen + analisis en ingles en 1 llamada -> JSON.
        Si no hay abstract, usa info del título para resumen metadata-based."""
        if not abstract or not abstract.strip():
            # Sin abstract: generar resumen breve basado en título
            if not title.strip():
                return {}
            prompt = (
                "This article has NO abstract. Based ONLY on the title, "
                "generate a brief summary and analysis. "
                "Do NOT invent results. Use hedging language.\n\n"
                "Return ONLY a valid JSON:\n"
                '{"summary": "Brief metadata-based summary (80-120 words)",\n'
                '"analysis": "Brief analysis noting this is metadata-only"}\n\n'
                f"Title: {title}\nAuthors: {authors}\n\n"
                "Return ONLY JSON."
            )
        else:
            prompt = (
                "Analyze this scientific article and return ONLY a valid JSON "
                "object with two keys:\n\n"
                '{"summary": "Concise summary in English (150-250 words) covering: '
                "objectives, methodology, key findings, conclusions, and relevance "
                'to water dissociation/recombination in electromembrane systems.",'
                '\n"analysis": "Structured analysis in English (200-350 words) with '
                "sections: 1. TYPE (theoretical/experimental/review/mixed), "
                "2. METHODOLOGY, 3. KEY FINDINGS (2-3 bullet points), "
                '4. EMS RELEVANCE, 5. LIMITATIONS, 6. RATING N/10."}\n\n'
                f"Title: {title}\nAuthors: {authors}\nAbstract: {abstract}\n\n"
                "Return ONLY the JSON. No markdown code blocks. No extra text."
            )

        data = self._call_openrouter_json(prompt, max_tokens=1200)
        if data:
            return data

        # Fallback: llamadas individuales
        logger.info("Batch summary+analysis fallo, usando fallback individual")
        result: dict = {}
        summary = self._call_openrouter(
            f"Summarize in English (150-250 words) focusing on objectives, "
            f"methodology, key findings, and relevance to water "
            f"dissociation/recombination in electromembrane systems.\n\n"
            f"Title: {title}\nAbstract: {abstract}\n\n"
            f"Provide ONLY the summary.",
            max_tokens=500,
        )
        if summary:
            result["summary"] = summary.strip()
        analysis = self._call_openrouter(
            "Analyze this scientific article with sections:\n"
            "1. TYPE (theoretical/experimental/review/mixed)\n"
            "2. METHODOLOGY\n3. KEY FINDINGS (2-3 bullet points)\n"
            "4. EMS RELEVANCE\n5. LIMITATIONS\n6. RATING N/10\n\n"
            f"Title: {title}\nAuthors: {authors}\n"
            f"Abstract: {abstract}\n\nBe concise (200-350 words).",
            max_tokens=600,
        )
        if analysis:
            result["analysis"] = analysis.strip()
        return result

    def _batch_translate_sa(
        self, summary: str, analysis: str,
    ) -> dict:
        """Traduce resumen + analisis a ES y RU en 1 llamada -> JSON."""
        fields: dict[str, str] = {}
        if summary:
            fields["ai_summary_es"] = "summary in Spanish"
            fields["ai_summary_ru"] = "summary in Russian"
        if analysis:
            fields["ai_analysis_es"] = "analysis in Spanish"
            fields["ai_analysis_ru"] = "analysis in Russian"
        if not fields:
            return {}

        schema = json.dumps(fields, ensure_ascii=False)
        prompt = (
            "Translate the following texts. Return ONLY a valid JSON with "
            f"these keys:\n{schema}\n\n"
            f"SUMMARY (English):\n{summary or '(none)'}\n\n"
            f"ANALYSIS (English):\n{analysis or '(none)'}\n\n"
            "Rules:\n"
            "- Preserve LaTeX/math, chemical formulas, abbreviations\n"
            "- Keep numbered sections and bullet points\n"
            "- Return ONLY the JSON, no markdown, no explanation"
        )

        data = self._call_openrouter_json(prompt, max_tokens=1400)
        if data:
            return data

        # Fallback: traducciones individuales
        logger.info("Batch translate SA fallo, usando fallback individual")
        result: dict = {}
        if summary:
            result["ai_summary_es"] = self._translate(summary, "es")
            result["ai_summary_ru"] = self._translate(summary, "ru")
        if analysis:
            result["ai_analysis_es"] = self._translate(analysis, "es")
            result["ai_analysis_ru"] = self._translate(analysis, "ru")
        return result

    # ================================================================
    # Individual translate (fallback)
    # ================================================================

    def _translate(self, text: str, target_lang: str = "es") -> str:
        """Traduce un texto individual. Usado como fallback cuando batch falla."""
        if not text or not text.strip():
            return ""
        lang_names = {"es": "Spanish", "en": "English", "ru": "Russian"}
        prompt = (
            f"Translate to {lang_names.get(target_lang, 'English')} ONLY. "
            f"No explanations. Return translation only:\n\n{text}"
        )
        try:
            response = self._call_openrouter(prompt, max_tokens=300)
            return response.strip() if response else ""
        except OpenRouterError:
            raise  # Propagar errores tipificados
        except Exception as e:
            logger.error("Error en traduccion a %s: %s", target_lang, e)
            return ""

    # ================================================================
    # Core API calls
    # ================================================================

    def _call_openrouter_json(
        self, prompt: str, max_tokens: int = 1000,
    ) -> Optional[dict]:
        """
        Llama a OpenRouter y parsea JSON de la respuesta.
        Maneja markdown code fences, texto extra, etc.
        Retorna None si falla el parseo JSON (pero propaga OpenRouterError).
        
        Logs de diagnóstico:
        - completion_tokens: tokens devueltos
        - finish_reason: 'stop' (ok), 'length' (truncado!)
        - content_length: chars devueltos
        """
        try:
            raw = self._call_openrouter(prompt, max_tokens=max_tokens)
        except OpenRouterError:
            raise  # Propagar errores tipificados
        if not raw:
            return None

        text = raw.strip()
        # Quitar ``` ... ``` si el modelo envuelve en code fence
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*\n?", "", text)
            text = re.sub(r"\n?```\s*$", "", text)

        try:
            logger.debug(
                "JSON parsed OK: lenght=%d, max_tokens=%d",
                len(text), max_tokens,
            )
            return json.loads(text)
        except json.JSONDecodeError:
            # Intentar extraer JSON de texto circundante: desde primera { hasta ultima }
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    extracted = json.loads(text[start:end+1])
                    logger.info(
                        "JSON extracted from position %d-%d (len=%d)",
                        start, end, len(text),
                    )
                    return extracted
                except json.JSONDecodeError:
                    pass
            logger.warning(
                "JSON parse failed: length=%d, max_tokens=%d, first_300=%s",
                len(text), max_tokens, text[:300],
            )
            return None

    def _call_openrouter(
        self, prompt: str, max_tokens: int = 500,
    ) -> Optional[str]:
        """
        Llamada generica a OpenRouter API con retry y fallback de modelos.

        Estrategia:
        1. Intenta con self.model (2 reintentos en 429 con backoff 1.5s, 3s).
        2. Si falla, prueba cada modelo en self._fallback_models (incluye premium sii configurado).
        3. Respeta _CALL_DEADLINE total para no exceder Gunicorn timeout.
        """
        models_to_try = [self.model] + [
            m for m in self._fallback_models if m != self.model
        ]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://agente-escribano.onrender.com",
            "X-Title": "Agente Escribano - Universidad",
            "Content-Type": "application/json",
        }

        deadline = time.monotonic() + _CALL_DEADLINE
        all_rate_limited = True

        for model in models_to_try:
            for attempt in range(_MAX_RETRIES_PER_MODEL + 1):
                # Abortar si se paso el deadline global
                remaining = deadline - time.monotonic()
                if remaining <= 2:
                    logger.warning(
                        "Deadline alcanzado (%.0fs). Abortando.",
                        _CALL_DEADLINE,
                    )
                    raise DeadlineExceededError(
                        f"Deadline de {_CALL_DEADLINE}s alcanzado"
                    )

                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": max_tokens,
                    "top_p": 0.9,
                }

                try:
                    # Ajustar read timeout al menor entre el configurado y el remaining
                    read_cap = min(self.timeout.read or 25.0, remaining)
                    req_timeout = httpx.Timeout(
                        connect=self.timeout.connect,
                        read=read_cap,
                        write=self.timeout.write,
                        pool=self.timeout.pool,
                    )
                    with httpx.Client(
                        timeout=req_timeout,
                    ) as client:
                        logger.debug(
                            "OpenRouter %s (intento %d), max_tokens=%d",
                            model, attempt + 1, max_tokens,
                        )
                        resp = client.post(
                            f"{self.base_url}/chat/completions",
                            headers=headers,
                            json=payload,
                        )
                        resp.raise_for_status()

                    try:
                        data = resp.json()
                    except (json.JSONDecodeError, ValueError) as e:
                        logger.warning(
                            "OpenRouter resp.json() fallo con %s: %s. Body: %s",
                            model, e, resp.text[:200],
                        )
                        all_rate_limited = False
                        break  # probar siguiente modelo

                    if not data.get("choices"):
                        logger.warning(
                            "OpenRouter sin choices (%s): %s", model, data,
                        )
                        all_rate_limited = False
                        break  # Probar siguiente modelo

                    content = (
                        data["choices"][0]
                        .get("message", {})
                        .get("content", "")
                    )
                    finish_reason = data["choices"][0].get("finish_reason", "?")
                    completion_tokens = data.get("usage", {}).get(
                        "completion_tokens", 0
                    )
                    
                    if not content:
                        logger.warning(
                            "OpenRouter content vacio (%s)", model,
                        )
                        all_rate_limited = False
                        break  # Probar siguiente modelo

                    if model != self.model:
                        logger.info(
                            "OpenRouter: %s funciono como fallback "
                            "(modelo principal %s no disponible)",
                            model, self.model,
                        )
                    logger.info(
                        "OpenRouter OK: model=%s, len=%d chars, "
                        "completion_tokens=%d, finish_reason=%s, max_tokens=%d",
                        model, len(content), completion_tokens,
                        finish_reason, max_tokens,
                    )
                    # DIAGNOSTICO: si finish_reason='length', el output fue truncado
                    if finish_reason == "length":
                        logger.warning(
                            "⚠️  TRUNCADO (finish_reason=length): "
                            "model=%s, max_tokens=%d insuficientes para "
                            "completion_tokens=%d",
                            model, max_tokens, completion_tokens,
                        )
                    return content.strip()

                except httpx.HTTPStatusError as e:
                    code = e.response.status_code
                    body = e.response.text[:500]
                    logger.warning(
                        "OpenRouter HTTP %d (%s, intento %d): %s",
                        code, model, attempt + 1, body[:200],
                    )
                    # 429 = rate limit -> reintentar con backoff exponencial
                    if code == 429 and attempt < _MAX_RETRIES_PER_MODEL:
                        delay = _RETRY_BASE_DELAY * (2 ** attempt)
                        logger.info(
                            "Rate-limited en %s, espera %.0fs (intento %d)...",
                            model, delay, attempt + 1,
                        )
                        time.sleep(delay)
                        continue
                    # 429 agotado retries -> probar siguiente modelo
                    if code == 429:
                        break
                    # 401/403 son fatales (auth)
                    if code in (401, 403):
                        raise AuthError(
                            f"OpenRouter auth error {code}: {body[:200]}"
                        ) from e
                    # 404 modelo no encontrado
                    if code == 404:
                        if model == self.model:
                            # Fatal solo si es el modelo principal
                            raise ModelNotFoundError(
                                f"Modelo no encontrado ({model}): {body[:200]}"
                            ) from e
                        # Fallback 404 -> saltar al siguiente
                        logger.warning(
                            "Fallback %s no encontrado (404), probando siguiente...",
                            model,
                        )
                        all_rate_limited = False
                        break
                                    # 400 = modelo ID inválido -> saltar al siguiente (no fatal)
                    if code == 400:
                        logger.warning(
                            "Modelo %s inválido (400), probando siguiente: %s",
                            model, body[:200],
                        )
                        all_rate_limited = False
                        break
                    # Otros 4xx son fatales
                    if 400 < code < 500:
                        raise OpenRouterError(
                            f"OpenRouter error {code}: {body[:200]}",
                            code="unknown",
                        ) from e
                        # 5xx -> probar siguiente modelo
                        all_rate_limited = False
                        break

                except httpx.TimeoutException:
                    logger.warning(
                        "OpenRouter timeout (read=%.0fs) con %s",
                        self.timeout.read or 25.0, model,
                    )
                    all_rate_limited = False
                    break  # Probar siguiente modelo

                except Exception as e:
                    err_str = str(e)
                    # json.JSONDecodeError (truncado o mal formado) → no es fatal,
                    # probar siguiente modelo en lugar de abortar todo el pipeline.
                    if "Expecting value" in err_str or isinstance(e, (ValueError, json.JSONDecodeError)):
                        logger.warning(
                            "OpenRouter JSON parse error con %s (posible truncado), "
                            "probando siguiente modelo: %s",
                            model, err_str[:200],
                        )
                        all_rate_limited = False
                        break  # saltar al siguiente modelo
                    # Cualquier otro error sí es fatal
                    logger.error(
                        "OpenRouter error con %s: %s", model, err_str[:500],
                    )
                    raise

            # Agotados reintentos para este modelo
            logger.info(
                "Modelo %s no disponible, probando siguiente...", model,
            )

        logger.error(
            "Todos los modelos agotados (%.0fs). Principal: %s",
            _CALL_DEADLINE, self.model,
        )
        if all_rate_limited:
            raise RateLimitError(
                f"Todos los modelos rate-limited ({_CALL_DEADLINE}s). "
                f"Principal: {self.model}"
            )
        raise NoContentError(
            f"Ningún modelo generó contenido ({_CALL_DEADLINE}s). "
            f"Principal: {self.model}"
        )

