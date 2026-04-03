"""
OpenRouter LLM Service para produccion.
Alternativa a Ollama cuando se despliega en Render con plan gratuito.

API: https://openrouter.ai/api/v1
Documentacion: https://openrouter.ai/docs

Optimizado: 3 llamadas API batch (en vez de 12 secuenciales).
"""
import logging
import json
import re
from typing import Optional

import httpx
from django.conf import settings

from apps.articles.models import Article

logger = logging.getLogger(__name__)

# Campos que se actualizan al procesar un articulo.
_AI_UPDATE_FIELDS = [
    "title_es", "title_en", "title_ru",
    "abstract_es", "abstract_en", "abstract_ru",
    "ai_summary", "ai_summary_es", "ai_summary_en", "ai_summary_ru",
    "ai_analysis", "ai_analysis_es", "ai_analysis_en", "ai_analysis_ru",
    "ai_processed",
]


class OpenRouterService:
    """
    Servicio que usa OpenRouter API para analisis y resumen de articulos.
    Compatible con la misma interfaz que OllamaService.

    Optimizado: 3 llamadas API batch con respuesta JSON en vez de 12.
    Fallback: si el parseo JSON falla, usa llamadas individuales.
    """

    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        self.base_url = "https://openrouter.ai/api/v1"
        self.model = getattr(settings, "OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct:free")
        self.timeout = 120.0  # 2 minutos

    # ================================================================
    # Punto de entrada principal
    # ================================================================

    def process_article(self, article: Article) -> dict:
        """
        Procesa un articulo: traduce, resume y analiza con 3 llamadas batch.
        Guarda campos actualizados directamente en la BD.

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

            # -- Paso 2: generar resumen + analisis en ingles (1 llamada) --
            best_abstract = (
                article.abstract_en
                or article.abstract_original
                or article.title
            )
            authors = article.authors[:200] if article.authors else "Unknown"

            if not article.ai_summary or not article.ai_analysis:
                sa = self._generate_summary_and_analysis(
                    article.title, best_abstract, authors,
                )
                if sa.get("summary") and not article.ai_summary:
                    article.ai_summary = sa["summary"]
                    article.ai_summary_en = sa["summary"]
                    result["ai_summary"] = sa["summary"]
                if sa.get("analysis") and not article.ai_analysis:
                    article.ai_analysis = sa["analysis"]
                    article.ai_analysis_en = sa["analysis"]
                    result["ai_analysis"] = sa["analysis"]

            # -- Paso 3: traducir resumen + analisis a ES/RU (1 llamada) --
            need_sa_tr = (
                (article.ai_summary and (
                    not article.ai_summary_es or not article.ai_summary_ru
                ))
                or (article.ai_analysis and (
                    not article.ai_analysis_es or not article.ai_analysis_ru
                ))
            )
            if need_sa_tr:
                sa_tr = self._batch_translate_sa(
                    article.ai_summary, article.ai_analysis,
                )
                for key in (
                    "ai_summary_es", "ai_summary_ru",
                    "ai_analysis_es", "ai_analysis_ru",
                ):
                    val = sa_tr.get(key)
                    if val and not getattr(article, key):
                        setattr(article, key, val)
                        result[key] = val

            article.ai_processed = True
            article.save(update_fields=_AI_UPDATE_FIELDS)
            logger.info(
                "Articulo %s procesado con OpenRouter (modelo: %s)",
                article.id, self.model,
            )
            return result

        except Exception as e:
            logger.error(
                "Error fatal procesando articulo %s con OpenRouter: %s",
                article.id, e,
            )
            article.save()
            raise

    # ================================================================
    # Batch methods  (1 API call each)
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

        data = self._call_openrouter_json(prompt, max_tokens=1500)
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

        data = self._call_openrouter_json(prompt, max_tokens=2000)
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
        """
        raw = self._call_openrouter(prompt, max_tokens=max_tokens)
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
            # Intentar extraer JSON de texto circundante
            match = re.search(
                r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL,
            )
            if match:
                try:
                    return json.loads(match.group())
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
        Llamada generica a OpenRouter API.
        Retorna texto crudo o None si falla.
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://agente-escribano.onrender.com",
            "X-Title": "Agente Escribano - Universidad",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": max_tokens,
            "top_p": 0.9,
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                logger.debug(
                    "OpenRouter %s, max_tokens=%d", self.model, max_tokens,
                )
                resp = client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()

            data = resp.json()
            if not data.get("choices"):
                logger.warning("OpenRouter sin choices: %s", data)
                return None

            content = (
                data["choices"][0].get("message", {}).get("content", "")
            )
            if not content:
                logger.warning("OpenRouter content vacio")
                return None

            logger.debug("OpenRouter: %d caracteres", len(content))
            return content.strip()

        except httpx.HTTPStatusError as e:
            logger.error(
                "OpenRouter HTTP %d: %s",
                e.response.status_code,
                e.response.text[:500],
            )
            return None
        except httpx.TimeoutException:
            logger.error("OpenRouter timeout (>%ds)", self.timeout)
            return None
        except Exception as e:
            logger.error("OpenRouter error: %s", str(e)[:500])
            return None

