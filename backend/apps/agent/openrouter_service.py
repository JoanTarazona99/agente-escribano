"""
OpenRouter LLM Service para demostración en producción.
Alternativa a Ollama cuando se despliega en Render con plan gratuito.

API: https://openrouter.ai/api/v1
Documentación: https://openrouter.ai/docs
Modelos gratuitos: gpt-3.5-turbo, openrouter/auto, etc.
"""
import logging
import json
from typing import Optional

import httpx
from django.conf import settings

from apps.articles.models import Article

logger = logging.getLogger(__name__)


class OpenRouterService:
    """
    Servicio que usa OpenRouter API para análisis y resumen de artículos.
    Compatible con la misma interfaz que OllamaService.
    
    Usa modelos gratuitos de OpenRouter (gpt-3.5-turbo, etc.)
    """

    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        self.base_url = "https://openrouter.ai/api/v1"
        # Usar modelo económico gratuito (gpt-3.5-turbo está disponible)
        self.model = "gpt-3.5-turbo"
        self.timeout = 120.0  # 2 minutos

    def process_article(self, article: Article) -> dict:
        """
        Procesa un artículo: traduce título/abstract, genera análisis y resumen.
        Retorna dict con campos actualizados.

        Args:
            article: Instancia de Article

        Returns:
            dict con claves: title_es, title_en, abstract_es, abstract_en,
                            ai_summary, ai_analysis
        """
        if not self.api_key:
            logger.warning("⚠️ OPENROUTER_API_KEY no configurada. Saltando análisis.")
            return {}

        result = {}

        try:
            # 1. Traducir título a ES/EN si es necesario
            if article.language_original not in ("es", "en"):
                result["title_es"] = self._translate(article.title, target_lang="es")
                result["title_en"] = self._translate(article.title, target_lang="en")
            else:
                result["title_es"] = (
                    article.title if article.language_original == "es" 
                    else self._translate(article.title, target_lang="es")
                )
                result["title_en"] = (
                    article.title if article.language_original == "en" 
                    else self._translate(article.title, target_lang="en")
                )

            # 2. Traducir abstract a ES/EN
            if article.abstract_original:
                result["abstract_es"] = self._translate(article.abstract_original, target_lang="es")
                result["abstract_en"] = self._translate(article.abstract_original, target_lang="en")

            # 3. Generar resumen (150-250 palabras)
            result["ai_summary"] = self._summarize(
                title=article.title,
                abstract=article.abstract_original or "",
            )

            # 4. Generar análisis detallado (200-350 palabras, 6 secciones obligatorias)
            result["ai_analysis"] = self._analyze(
                title=article.title,
                abstract=article.abstract_original or "",
                authors=", ".join(article.authors[:3]) if article.authors else "Unknown",
            )

            result["ai_processed"] = True
            logger.info("✅ Artículo %s procesado con OpenRouter (modelo: %s)", article.id, self.model)
            return result

        except Exception as e:
            logger.error("❌ Error fatal procesando artículo %s con OpenRouter: %s", article.id, e)
            return {}

    def _translate(self, text: str, target_lang: str = "es") -> str:
        """Traduce texto a idioma destino usando OpenRouter."""
        if not text or len(text.strip()) == 0:
            return ""

        lang_names = {"es": "Spanish", "en": "English", "ru": "Russian"}
        lang_name = lang_names.get(target_lang, "English")

        prompt = f"Translate to {lang_name} ONLY. No explanations. Return translation only:\n\n{text}"

        try:
            response = self._call_openrouter(prompt, max_tokens=300)
            return response.strip() if response else ""
        except Exception as e:
            logger.error("❌ Error en traducción a %s: %s", target_lang, e)
            return ""

    def _summarize(self, title: str, abstract: str) -> str:
        """Genera resumen conciso del artículo (150-250 palabras)."""
        if not abstract or len(abstract.strip()) == 0:
            return ""

        prompt = f"""Summarize in Spanish (150-250 words) focusing on:
- Main objectives
- Methodology  
- Key findings
- Conclusions
- Relevance to water dissociation/recombination in electromembrane systems

Title: {title}

Abstract: {abstract}

Provide ONLY the summary, no labels or numbering."""

        try:
            response = self._call_openrouter(prompt, max_tokens=500)
            return response.strip() if response else ""
        except Exception as e:
            logger.error("❌ Error en resumen: %s", e)
            return ""

    def _analyze(self, title: str, abstract: str, authors: str = "") -> str:
        """
        Genera análisis detallado en 200-350 palabras con 6 secciones obligatorias.
        """
        if not abstract or len(abstract.strip()) == 0:
            return ""

        # Prompt en ruso para análisis detallado (compatible con formato esperado)
        prompt = """Проанализируй статью по этой схеме СТРОГО В ЭТОМ ПОРЯДКЕ:

СЕКЦИИ (все обязательны):
1. ТИП: одно слово (теоретическая/экспериментальная/обзор/смешанная)
2. МЕТОДОЛОГИЯ: Техники и методы (1-2 предложения)
3. КЛЮЧЕВЫЕ РЕЗУЛЬТАТЫ: Основные выводы (2-3 пункта)
4. РЕЛЕВАНТНОСТЬ ЭМС: Связь с диссоциацией/рекомбинацией воды в ЭМС (1-2 предложения)
5. ОГРАНИЧЕНИЯ: Слабые стороны (1-2 предложения)
6. ОЦЕНКА: N/10 — краткое обоснование в 1 предложении

Общая длина: 200-350 слов. Пиши компактно и точно.

Статья:
Заголовок: """ + title + """
Авторы: """ + authors + """
Аннотация: """ + abstract

        try:
            response = self._call_openrouter(prompt, max_tokens=600)
            if response:
                # Post-process: remover marcadores de cierre si existen
                response = response.replace("КОНЕЦ", "").strip()
            return response if response else ""
        except Exception as e:
            logger.error("❌ Error en análisis: %s", e)
            return ""

    def _call_openrouter(self, prompt: str, max_tokens: int = 500) -> Optional[str]:
        """
        Llamada genérica a OpenRouter API siguiendo la documentación oficial.
        
        Args:
            prompt: Instrucción/pregunta para el modelo
            max_tokens: Máximo de tokens en la respuesta

        Returns:
            Contenido del primer choice de la respuesta o None si falla
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://agente-escribano.onrender.com",  # Por buena práctica
            "X-Title": "Agente Escribano - Universidad",
            "Content-Type": "application/json",
        }

        # Payload siguiendo documentación oficial de OpenRouter
        payload = {
            "model": self.model,  # Usar modelo gratuito configurado
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,  # Bajo para respuestas consistentes
            "max_tokens": max_tokens,
            "top_p": 0.9,
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                logger.debug(f"📡 Llamando OpenRouter con modelo: {self.model}, max_tokens: {max_tokens}")
                
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,  # httpx maneja JSON automáticamente
                )
                response.raise_for_status()

            data = response.json()
            
            # Validar estructura de respuesta
            if not data.get("choices"):
                logger.warning("⚠️ OpenRouter respuesta sin choices: %s", data)
                return None
                
            choice = data["choices"][0]
            message = choice.get("message", {})
            content = message.get("content", "")
            
            if not content:
                logger.warning("⚠️ OpenRouter message sin content: %s", message)
                return None

            logger.debug(f"✅ OpenRouter respondió: {len(content)} caracteres")
            return content.strip()

        except httpx.HTTPStatusError as e:
            error_text = e.response.text
            logger.error(
                "❌ OpenRouter HTTP error %d: %s",
                e.response.status_code,
                error_text[:500]  # Log primeros 500 chars del error
            )
            # Intentar parsear error específico
            try:
                error_data = e.response.json()
                if error_data.get("error"):
                    logger.error("   Detalle del error: %s", error_data["error"])
            except:
                pass
            return None
            
        except httpx.TimeoutException:
            logger.error("❌ OpenRouter timeout (>%ds)", self.timeout)
            return None
            
        except Exception as e:
            logger.error("❌ Error inesperado llamando OpenRouter: %s", str(e)[:500])
            return None

