"""
Servicio de integración con Ollama (local) o OpenRouter (producción).

Uso:
    service = get_llm_service()  # Elige automáticamente según LLM_PROVIDER
    service.process_article(article)  # actualiza campos ai_* en el objeto

Mocking en tests:
    with unittest.mock.patch("apps.agent.services.ollama.Client") as mock_client:
        ...
"""
from __future__ import annotations

import logging
import os

from django.conf import settings

# Importar OpenRouterService (evita import circular si se necesita)
try:
    from .openrouter_service import OpenRouterService
except ImportError:
    OpenRouterService = None

# ─── Bypass proxy del sistema para peticiones a Ollama (localhost) ────────────
# httpx (usado internamente por ollama) detecta el proxy del registro de Windows
# (p.ej. V2Ray/Clash en 127.0.0.1:10809) y enruta TODAS las peticiones HTTP a
# través de él — incluido localhost:11434 — provocando 503.
# Forzamos NO_PROXY (sobrescribiendo, no setdefault) para que httpx excluya
# localhost del proxy. No tocamos HTTP_PROXY/HTTPS_PROXY porque otros módulos
# (conectores arXiv, etc.) podrían necesitarlos.
os.environ["NO_PROXY"] = "localhost,127.0.0.1,0.0.0.0"

logger = logging.getLogger(__name__)


# ─── Factory pattern: selecciona el servicio LLM según configuración ──────────
def get_llm_service():
    """
    Retorna la instancia del servicio LLM según LLM_PROVIDER en settings.

    Valores permitidos:
    - 'openrouter': Usa OpenRouter API (producción, Render gratuito)
    - 'ollama': Usa Ollama local (desarrollo, completamente gratis)

    En .env.dev (desarrollo):  LLM_PROVIDER=ollama
    En .env (Render):          LLM_PROVIDER=openrouter
    """
    provider = getattr(settings, "LLM_PROVIDER", "ollama")

    if provider == "openrouter" and OpenRouterService:
        logger.info("🌐 Usando OpenRouter como provedor LLM")
        return OpenRouterService()
    else:
        logger.info("🦙 Usando Ollama como provedor LLM")
        return OllamaService()


# ─── Templates de prompts ─────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "Eres un analista científico experto en electroquímica, membranas de intercambio "
    "iónico y sistemas electromembrana (ЭМС). Respondes siempre en el idioma que se "
    "te indica, de forma precisa y concisa."
)

TRANSLATE_TO_ES_PROMPT = """Traduce el siguiente texto científico al ESPAÑOL.
Mantén los términos técnicos precisos. Devuelve SOLO la traducción.

Texto:
{text}"""

TRANSLATE_TO_EN_PROMPT = """Translate the following scientific text to ENGLISH.
Keep technical terms precise. Return ONLY the translation.

Text:
{text}"""

TRANSLATE_TO_RU_PROMPT = """Переведи следующий научный текст на РУССКИЙ язык.
Сохрани точность научных терминов. Верни ТОЛЬКО перевод.

Текст:
{text}"""

SUMMARIZE_PROMPT = """Составь резюме следующей научной статьи на русском языке.
Отрази: основную цель, методологию, ключевые результаты, выводы и применимость.

ОГРАНИЧЕНИЯ ПО ДЛИНЕ: резюме должно содержать от 150 до 250 слов.
ОБЯЗАТЕЛЬНО доведи текст до логического завершения. Не обрывай предложения.
Если нужно сократить — перефразируй, но НИКОГДА не оставляй текст незавершённым.

Название: {title}
Аннотация: {abstract}

Резюме:"""

ANALYZE_PROMPT = """Проанализируй статью и верни краткий структурированный отчёт на русском языке.

Требования:
- Общая длина: 200–350 слов. Будь краток.
- НАПИШИ ВСЕ 6 секций полностью. Не обрывай ни одну.
- После секции 6 напиши слово «КОНЕЦ» на отдельной строке.

Секции:
1. **ТИП**: одно слово (теоретическая / экспериментальная / обзор / смешанная)
2. **МЕТОДОЛОГИЯ**: Техники и методы (1-2 предложения)
3. **КЛЮЧЕВЫЕ РЕЗУЛЬТАТЫ**: Основные выводы (2-3 пункта, по 1 предложению)
4. **РЕЛЕВАНТНОСТЬ ЭМС**: Связь с диссоциацией/рекомбинацией воды в ЭМС (1-2 предложения)
5. **ОГРАНИЧЕНИЯ**: Слабые стороны (1-2 предложения)
6. **ОЦЕНКА**: N/10 — краткое обоснование в 1 предложении

Название: {title}
Аннотация: {abstract}

Анализ:"""


class OllamaService:
    """
    Servicio para procesar artículos científicos usando Ollama/LLaMA.
    """

    def __init__(self) -> None:
        try:
            import ollama
        except ImportError:
            raise ImportError("ollama is not installed. Set LLM_PROVIDER=openrouter for production.")
        
        base_url = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = getattr(settings, "OLLAMA_MODEL", "llama3.2")
        self.client = ollama.Client(host=base_url, timeout=120.0)
        self.logger = logger

    def _chat(self, prompt: str, *, temperature: float = 0.3) -> str:
        """Envía un prompt al modelo y retorna el texto de respuesta."""
        try:
            response = self.client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                options={"temperature": temperature, "num_predict": 4096},
            )
            return response["message"]["content"].strip()
        except Exception as exc:
            self.logger.error("Error llamando a Ollama: %s", exc)
            raise

    def translate(self, text: str, target_lang: str = "es") -> str:
        """
        Traduce texto al idioma objetivo.

        Args:
            text: Texto a traducir.
            target_lang: "es" (español) o "en" (inglés).

        Returns:
            Texto traducido.
        """
        if not text or not text.strip():
            return ""

        if target_lang == "es":
            prompt = TRANSLATE_TO_ES_PROMPT.format(text=text)
        elif target_lang == "en":
            prompt = TRANSLATE_TO_EN_PROMPT.format(text=text)
        elif target_lang == "ru":
            prompt = TRANSLATE_TO_RU_PROMPT.format(text=text)
        else:
            raise ValueError(f"Idioma destino no soportado: {target_lang}")

        return self._chat(prompt, temperature=0.2)

    def summarize(self, title: str, abstract: str) -> str:
        """
        Genera un resumen en español del artículo.

        Args:
            title: Título del artículo.
            abstract: Abstract del artículo.

        Returns:
            Resumen en español (≤150 palabras).
        """
        if not abstract.strip() and not title.strip():
            return ""

        prompt = SUMMARIZE_PROMPT.format(
            title=title or "(sin título)",
            abstract=abstract or "(sin abstract)",
        )
        return self._chat(prompt, temperature=0.5)

    def analyze(self, title: str, abstract: str) -> str:
        """
        Genera un análisis estructurado del artículo en español.

        Args:
            title: Título del artículo.
            abstract: Abstract del artículo.

        Returns:
            Análisis estructurado con tipo, metodología, relevancia y hallazgos.
        """
        if not abstract.strip() and not title.strip():
            return ""

        prompt = ANALYZE_PROMPT.format(
            title=title or "(sin título)",
            abstract=abstract or "(sin abstract)",
        )
        result = self._chat(prompt, temperature=0.3)

        # Limpiar marca de fin si el modelo la escribió
        result = result.replace("КОНЕЦ", "").strip()

        # Detectar truncamiento: si falta alguna sección, logear advertencia
        for marker in ["ТИП", "МЕТОДОЛОГИЯ", "КЛЮЧЕВЫЕ РЕЗУЛЬТАТЫ",
                        "РЕЛЕВАНТНОСТЬ ЭМС", "ОГРАНИЧЕНИЯ", "ОЦЕНКА"]:
            if marker not in result:
                self.logger.warning(
                    "Análisis posiblemente truncado: falta sección '%s'", marker
                )
                break

        return result

    def process_article(self, article) -> None:  # noqa: ANN001
        """
        Procesa un artículo completo: traduce, resume y analiza.
        Actualiza los campos ai_* directamente en el objeto y guarda en BD.

        Args:
            article: Instancia de apps.articles.models.Article.
        """
        self.logger.info("Procesando artículo ID=%s: %s", article.pk, article.title[:60])

        text_for_translation = article.abstract_original or article.title
        lang = article.language_original or "ru"

        # Traducciones (solo si no están en el idioma ya)
        if lang != "es" and not article.abstract_es:
            article.abstract_es = self.translate(text_for_translation, target_lang="es")
        if lang != "es" and not article.title_es:
            article.title_es = self.translate(article.title, target_lang="es")

        if lang != "en" and not article.abstract_en:
            article.abstract_en = self.translate(text_for_translation, target_lang="en")
        if lang != "en" and not article.title_en:
            article.title_en = self.translate(article.title, target_lang="en")

        if lang != "ru" and not article.abstract_ru:
            article.abstract_ru = self.translate(text_for_translation, target_lang="ru")
        if lang != "ru" and not article.title_ru:
            article.title_ru = self.translate(article.title, target_lang="ru")

        # Resumen y análisis — generar en RU y traducir a ES/EN
        best_abstract = article.abstract_en or article.abstract_ru or article.abstract_es or article.abstract_original
        best_title = article.title_en or article.title_ru or article.title_es or article.title

        # Generar resumen y análisis base en ruso
        summary_ru = self.summarize(best_title, best_abstract)
        analysis_ru = self.analyze(best_title, best_abstract)

        article.ai_summary_ru = summary_ru
        article.ai_analysis_ru = analysis_ru
        article.ai_summary = summary_ru  # legacy
        article.ai_analysis = analysis_ru  # legacy

        # Traducir resumen a ES y EN
        article.ai_summary_es = self.translate(summary_ru, target_lang="es")
        article.ai_summary_en = self.translate(summary_ru, target_lang="en")

        # Traducir análisis a ES y EN
        article.ai_analysis_es = self.translate(analysis_ru, target_lang="es")
        article.ai_analysis_en = self.translate(analysis_ru, target_lang="en")

        article.ai_processed = True

        article.save(update_fields=[
            "title_es", "title_en", "title_ru",
            "abstract_es", "abstract_en", "abstract_ru",
            "ai_summary", "ai_summary_es", "ai_summary_en", "ai_summary_ru",
            "ai_analysis", "ai_analysis_es", "ai_analysis_en", "ai_analysis_ru",
            "ai_processed",
        ])

        self.logger.info("Artículo ID=%s procesado correctamente.", article.pk)
