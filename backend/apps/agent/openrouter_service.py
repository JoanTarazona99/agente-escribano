"""
OpenRouter LLM Service para produccion.
Alternativa a Ollama cuando se despliega en Render con plan gratuito.

API: https://openrouter.ai/api/v1
Documentacion: https://openrouter.ai/docs

Optimizado: 2 llamadas API batch (15-20s cada una, 80s total << 300s timeout).
Resiliente: retry con backoff en 429 + fallback a modelos alternativos.
"""
import logging
import json
import re
import time
from typing import Optional

import httpx
from django.conf import settings

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

# Modelos gratuitos de fallback, ordenados por preferencia.
# Whitelist estricta: solo slugs :free verificados en OpenRouter.
# Si el principal da 429/404, se prueban estos. Duplicados con
# self.model se filtran automaticamente.
_FALLBACK_MODELS = [
    "qwen/qwen3.6-plus:free",
    "qwen/qwen3.6-plus-preview:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
]

# Reintentos en 429 antes de saltar al siguiente modelo.
_MAX_RETRIES_PER_MODEL = 2
# Base para backoff exponencial: delay = base * 2^attempt (2s, 4s).
_RETRY_BASE_DELAY = 2.0
# Tiempo maximo total para _call_openrouter (segundos).
# Con 2 batch calls secuenciales: mega-prompt ~50s + batch_translate ~50s = 100s,
# que deja margen frente al timeout de django-q2 (300s) para que el except
# pueda limpiar la BD antes del kill.
_CALL_DEADLINE = 120.0


class OpenRouterService:
    """
    Servicio que usa OpenRouter API para analisis y resumen de articulos.
    Compatible con la misma interfaz que OllamaService.

    Pipeline: 3 llamadas JSON:
    1. Traducir titulo + abstract a ES/EN/RU     (~20s, ~1200 tokens)
    2. Generar summary + analysis en EN           (~35s, ~900 tokens)
    3. Traducir summary + analysis a ES/RU        (~25s, ~1400 tokens)
    Total: ~80s << 300s timeout django-q2
    """

    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        self.base_url = "https://openrouter.ai/api/v1"
        self.model = getattr(settings, "OPENROUTER_MODEL", "qwen/qwen3.6-plus:free")
        # Timeout explicito por fase para evitar hang en lectura SSL stream.
        # connect=10s, read=50s (permite mega-prompt lento), write=10s, pool=5s.
        self.timeout = httpx.Timeout(connect=10.0, read=50.0, write=10.0, pool=5.0)

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

        result: dict = {}
        lang = article.language_original or "en"

        try:
            # -- Paso 1: traducir titulo + abstract a ES/EN/RU (1 llamada) --
            need_tr = (
                (article.title and any(
                    not getattr(article, f"title_{l}")
                    for l in ("es", "en", "ru") if l != lang
                ))
                or (article.abstract_original and any(
                    not getattr(article, f"abstract_{l}")
                    for l in ("es", "en", "ru") if l != lang
                ))
            )
            if need_tr:
                tr = self._batch_translate(
                    article.title, article.abstract_original, lang,
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
                article.abstract_en
                or article.abstract_original
                or article.title
            )
            authors = article.authors[:200] if article.authors else "Unknown"

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
    ) -> dict:
        """
        2 llamadas pequeñas en vez de 1 mega-prompt:
        Llamada 1: Generar summary + analysis en EN (~900 tokens, ~35s)
        Llamada 2: Traducir a ES + RU               (~1400 tokens, ~45s)
        Total: ~80s << 300s timeout django-q2

        Returns:
            dict con claves: summary_en, summary_es, summary_ru,
                             analysis_en, analysis_es, analysis_ru.
        """
        if not abstract or not abstract.strip():
            return {}

        result: dict = {}

        # Llamada 1: generar resumen + analisis en EN
        sa = self._generate_summary_and_analysis(title, abstract, authors)
        if sa.get("summary"):
            result["summary_en"] = sa["summary"]
        if sa.get("analysis"):
            result["analysis_en"] = sa["analysis"]

        if not result:
            return {}

        # Llamada 2: traducir a ES + RU
        sa_tr = self._batch_translate_sa(
            result.get("summary_en", ""),
            result.get("analysis_en", ""),
        )
        result["summary_es"] = sa_tr.get("ai_summary_es", "")
        result["summary_ru"] = sa_tr.get("ai_summary_ru", "")
        result["analysis_es"] = sa_tr.get("ai_analysis_es", "")
        result["analysis_ru"] = sa_tr.get("ai_analysis_ru", "")

        return result

    def _generate_summary_and_analysis(
        self, title: str, abstract: str, authors: str,
    ) -> dict:
        """Genera resumen + analisis en ingles en 1 llamada -> JSON."""
        if not abstract or not abstract.strip():
            return {}

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
            return json.loads(text)
        except json.JSONDecodeError:
            # Intentar extraer JSON de texto circundante: desde primera { hasta ultima }
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start:end+1])
                except json.JSONDecodeError:
                    pass
            logger.warning(
                "No se pudo parsear JSON de OpenRouter: %s", text[:300],
            )
            return None

    def _call_openrouter(
        self, prompt: str, max_tokens: int = 500,
    ) -> Optional[str]:
        """
        Llamada generica a OpenRouter API con retry y fallback de modelos.

        Estrategia:
        1. Intenta con self.model (1 retry en 429).
        2. Si falla, prueba cada modelo en _FALLBACK_MODELS.
        3. Respeta _CALL_DEADLINE total para no exceder Gunicorn timeout.
        """
        models_to_try = [self.model] + [
            m for m in _FALLBACK_MODELS if m != self.model
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

                    data = resp.json()
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
                    logger.debug(
                        "OpenRouter: %d caracteres (%s)", len(content), model,
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
                    # Otros 4xx son fatales
                    if 400 <= code < 500:
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
                    logger.error(
                        "OpenRouter error con %s: %s", model, str(e)[:500],
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

