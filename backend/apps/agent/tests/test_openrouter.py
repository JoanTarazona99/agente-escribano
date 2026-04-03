"""Tests del OpenRouterService con mocks de httpx."""
import json

import httpx
import pytest
from unittest.mock import MagicMock, patch

from apps.agent.openrouter_service import (
    OpenRouterService,
    OpenRouterError,
    RateLimitError,
    AuthError,
    ModelNotFoundError,
    NoContentError,
    DeadlineExceededError,
)


# ── Helpers ──────────────────────────────────────────────────────────

def _openrouter_response(content: str) -> dict:
    """Simula la estructura de respuesta de OpenRouter API."""
    return {
        "choices": [{"message": {"content": content}}],
        "model": "meta-llama/llama-3.3-70b-instruct:free",
    }


def _make_httpx_response(json_body: dict, status_code: int = 200) -> httpx.Response:
    """Crea un httpx.Response fake."""
    resp = httpx.Response(
        status_code=status_code,
        json=json_body,
        request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
    )
    return resp


def _make_service() -> OpenRouterService:
    """Instancia el servicio con settings mockeados."""
    with patch.multiple(
        "apps.agent.openrouter_service.settings",
        OPENROUTER_API_KEY="test-key-123",
        OPENROUTER_MODEL="test-model",
    ):
        return OpenRouterService()


# ── Tests unitarios (sin DB) ────────────────────────────────────────


class TestCallOpenRouter:
    """Tests para _call_openrouter (llamada raw con retry + fallback)."""

    def test_returns_content_on_success(self):
        service = _make_service()
        mock_resp = _make_httpx_response(_openrouter_response("Hello world"))

        with patch("httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = lambda s: s
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            MockClient.return_value.post.return_value = mock_resp

            result = service._call_openrouter("test prompt")
            assert result == "Hello world"

    @patch("apps.agent.openrouter_service.time.monotonic")
    @patch("apps.agent.openrouter_service.time.sleep")
    def test_retries_on_429_then_falls_back(self, mock_sleep, mock_monotonic):
        """429 agota retries en modelo principal, luego fallback funciona."""
        service = _make_service()
        error_resp = _make_httpx_response({"error": "rate limited"}, status_code=429)
        ok_resp = _make_httpx_response(_openrouter_response("Fallback OK"))

        # Simular que siempre queda tiempo (deadline lejano)
        mock_monotonic.return_value = 0.0

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Intentos 1-3 (test-model: original + 2 retries): 429
            if call_count <= 3:
                return error_resp
            # Intento 4 (primer fallback): exito
            return ok_resp

        with patch("httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = lambda s: s
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            MockClient.return_value.post.side_effect = side_effect

            result = service._call_openrouter("test prompt")
            assert result == "Fallback OK"
            assert mock_sleep.call_count == 2  # 2 retries con backoff exponencial

    @patch("apps.agent.openrouter_service.time.monotonic")
    @patch("apps.agent.openrouter_service.time.sleep")
    def test_returns_none_when_all_models_exhausted(self, mock_sleep, mock_monotonic):
        """Si todos los modelos dan 429, lanza RateLimitError."""
        service = _make_service()
        error_resp = _make_httpx_response({"error": "rate limited"}, status_code=429)
        mock_monotonic.return_value = 0.0

        with patch("httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = lambda s: s
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            MockClient.return_value.post.return_value = error_resp

            with pytest.raises(RateLimitError):
                service._call_openrouter("test prompt")

    @patch("apps.agent.openrouter_service.time.monotonic")
    def test_returns_none_on_timeout_tries_next_model(self, mock_monotonic):
        """Timeout en modelo principal, fallback funciona."""
        service = _make_service()
        ok_resp = _make_httpx_response(_openrouter_response("Fallback"))
        mock_monotonic.return_value = 0.0
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.TimeoutException("timeout")
            return ok_resp

        with patch("httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = lambda s: s
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            MockClient.return_value.post.side_effect = side_effect

            result = service._call_openrouter("test prompt")
            assert result == "Fallback"

    def test_raises_on_4xx_model_not_found(self):
        """404 en modelo principal se propaga como ModelNotFoundError."""
        service = _make_service()
        error_resp = _make_httpx_response(
            {"error": {"message": "No endpoints found for model"}}, status_code=404,
        )

        with patch("httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = lambda s: s
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            MockClient.return_value.post.return_value = error_resp

            with pytest.raises(ModelNotFoundError):
                service._call_openrouter("test prompt")

    @patch("apps.agent.openrouter_service.time.monotonic")
    def test_404_on_fallback_skips_to_next(self, mock_monotonic):
        """404 en fallback no es fatal: salta al siguiente modelo."""
        service = _make_service()
        mock_monotonic.return_value = 0.0
        error_429 = _make_httpx_response({"error": "rate limited"}, status_code=429)
        error_404 = _make_httpx_response(
            {"error": {"message": "No endpoints found"}}, status_code=404,
        )
        ok_resp = _make_httpx_response(_openrouter_response("OK from later fallback"))
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 3:  # principal: 3 intentos -> 429
                return error_429
            if call_count == 4:  # primer fallback: 404
                return error_404
            return ok_resp  # segundo fallback: OK

        with patch("httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = lambda s: s
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            MockClient.return_value.post.side_effect = side_effect
            with patch("apps.agent.openrouter_service.time.sleep"):
                result = service._call_openrouter("test prompt")
                assert result == "OK from later fallback"

    def test_raises_on_401_invalid_key(self):
        """401 se propaga como AuthError."""
        service = _make_service()
        error_resp = _make_httpx_response(
            {"error": {"message": "Invalid credentials"}}, status_code=401,
        )

        with patch("httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = lambda s: s
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            MockClient.return_value.post.return_value = error_resp

            with pytest.raises(AuthError):
                service._call_openrouter("test prompt")

    def test_raises_no_content_when_no_choices(self):
        """Sin choices en todos los modelos lanza NoContentError."""
        service = _make_service()
        mock_resp = _make_httpx_response({"choices": []})

        with patch("httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = lambda s: s
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            MockClient.return_value.post.return_value = mock_resp

            with pytest.raises(NoContentError):
                service._call_openrouter("test prompt")


class TestCallOpenRouterJson:
    """Tests para _call_openrouter_json (parseo JSON)."""

    def test_parses_clean_json(self):
        service = _make_service()
        json_str = '{"title_es": "Hola", "title_ru": "Privet"}'
        with patch.object(service, "_call_openrouter", return_value=json_str):
            result = service._call_openrouter_json("prompt")
            assert result == {"title_es": "Hola", "title_ru": "Privet"}

    def test_strips_markdown_code_fence(self):
        service = _make_service()
        raw = '```json\n{"summary": "test"}\n```'
        with patch.object(service, "_call_openrouter", return_value=raw):
            result = service._call_openrouter_json("prompt")
            assert result == {"summary": "test"}

    def test_extracts_json_from_surrounding_text(self):
        service = _make_service()
        raw = 'Sure! Here is the result:\n{"key": "value"}\nHope this helps!'
        with patch.object(service, "_call_openrouter", return_value=raw):
            result = service._call_openrouter_json("prompt")
            assert result == {"key": "value"}

    def test_returns_none_on_invalid_json(self):
        service = _make_service()
        with patch.object(service, "_call_openrouter", return_value="not json at all"):
            result = service._call_openrouter_json("prompt")
            assert result is None

    def test_returns_none_when_call_returns_none(self):
        service = _make_service()
        with patch.object(service, "_call_openrouter", return_value=None):
            result = service._call_openrouter_json("prompt")
            assert result is None


class TestTranslate:
    """Tests para _translate (fallback individual)."""

    def test_returns_translation(self):
        service = _make_service()
        with patch.object(service, "_call_openrouter", return_value="  Hola mundo  "):
            result = service._translate("Hello world", "es")
            assert result == "Hola mundo"

    def test_returns_empty_for_empty_input(self):
        service = _make_service()
        result = service._translate("", "es")
        assert result == ""

    def test_returns_empty_on_api_failure(self):
        service = _make_service()
        with patch.object(service, "_call_openrouter", return_value=None):
            result = service._translate("text", "ru")
            assert result == ""


class TestBatchTranslate:
    """Tests para _batch_translate."""

    def test_batch_returns_translations_from_json(self):
        service = _make_service()
        batch_json = {
            "title_es": "Titulo ES",
            "title_ru": "Titulo RU",
            "abstract_es": "Abstract ES",
            "abstract_ru": "Abstract RU",
        }
        with patch.object(service, "_call_openrouter_json", return_value=batch_json):
            result = service._batch_translate("Title", "Abstract text", "en")
            assert result["title_es"] == "Titulo ES"
            assert result["abstract_ru"] == "Abstract RU"

    def test_batch_falls_back_to_individual_on_json_failure(self):
        service = _make_service()
        with patch.object(service, "_call_openrouter_json", return_value=None):
            with patch.object(service, "_translate", return_value="translated") as mock_tr:
                result = service._batch_translate("Title", "Abstract", "en")
                # Should call _translate for each missing lang: es, ru for title + es, ru for abstract
                assert mock_tr.call_count == 4
                assert result["title_es"] == "translated"

    def test_batch_returns_empty_when_no_text(self):
        service = _make_service()
        result = service._batch_translate("", "", "en")
        assert result == {}


class TestGenerateSummaryAndAnalysis:
    """Tests para _generate_summary_and_analysis."""

    def test_returns_summary_and_analysis(self):
        service = _make_service()
        sa_json = {
            "summary": "This is a summary of the study...",
            "analysis": "1. TYPE: experimental\n2. METHODOLOGY: ...",
        }
        with patch.object(service, "_call_openrouter_json", return_value=sa_json):
            result = service._generate_summary_and_analysis("Title", "Abstract", "Authors")
            assert "summary" in result
            assert "analysis" in result

    def test_falls_back_to_individual_on_json_failure(self):
        service = _make_service()
        with patch.object(service, "_call_openrouter_json", return_value=None):
            with patch.object(
                service, "_call_openrouter",
                side_effect=["Summary text", "Analysis text"],
            ):
                result = service._generate_summary_and_analysis("Title", "Abstract", "Auth")
                assert result["summary"] == "Summary text"
                assert result["analysis"] == "Analysis text"

    def test_returns_empty_when_no_abstract(self):
        service = _make_service()
        result = service._generate_summary_and_analysis("Title", "", "Authors")
        assert result == {}


# ── Tests de integración (con DB) ───────────────────────────────────


@pytest.mark.django_db
class TestProcessArticle:
    """Tests para process_article — flujo completo con BD."""

    def test_saves_all_ai_fields(self):
        from apps.articles.models import Article

        article = Article.objects.create(
            title="Water dissociation in EMS",
            abstract_original="Study of water recombination in electromembrane systems.",
            language_original="en",
        )

        service = _make_service()

        # Mock batch translate (call 1)
        batch_tr = {
            "title_es": "Disociacion del agua en EMS",
            "title_ru": "Dissociatsia vody v EMS",
            "abstract_es": "Estudio de recombinacion",
            "abstract_ru": "Issledovanie recombinatsii",
        }
        # Mock summary+analysis (call 2)
        sa = {
            "summary": "This study investigates water dissociation...",
            "analysis": "1. TYPE: experimental\n2. METHODOLOGY: voltammetry",
        }
        # Mock translate SA (call 3)
        sa_tr = {
            "ai_summary_es": "Este estudio investiga...",
            "ai_summary_ru": "Eto issledovanie...",
            "ai_analysis_es": "1. TIPO: experimental",
            "ai_analysis_ru": "1. TIP: eksperimentalnyj",
        }

        with patch.object(
            service, "_call_openrouter_json",
            side_effect=[batch_tr, sa, sa_tr],
        ):
            result = service.process_article(article)

        article.refresh_from_db()
        assert article.ai_processed is True
        assert article.title_es == "Disociacion del agua en EMS"
        assert article.title_ru == "Dissociatsia vody v EMS"
        assert article.abstract_es == "Estudio de recombinacion"
        assert article.ai_summary == "This study investigates water dissociation..."
        assert article.ai_summary_en == "This study investigates water dissociation..."
        assert article.ai_summary_es == "Este estudio investiga..."
        assert article.ai_analysis == "1. TYPE: experimental\n2. METHODOLOGY: voltammetry"
        assert article.ai_analysis_ru == "1. TIP: eksperimentalnyj"
        assert "title_es" in result

    def test_returns_empty_without_api_key(self):
        from apps.articles.models import Article

        article = Article.objects.create(
            title="Test", abstract_original="Abstract", language_original="en",
        )

        with patch.multiple(
            "apps.agent.openrouter_service.settings",
            OPENROUTER_API_KEY="",
            OPENROUTER_MODEL="test-model",
        ):
            service = OpenRouterService()
            result = service.process_article(article)

        assert result == {}
        article.refresh_from_db()
        assert article.ai_processed is False

    def test_propagates_error_and_saves_partial(self):
        from apps.articles.models import Article

        article = Article.objects.create(
            title="Test", abstract_original="Abstract", language_original="en",
        )

        service = _make_service()

        # First batch translate succeeds, then summary fails
        batch_tr = {"title_es": "Titulo", "title_ru": "Zagolovok"}
        with patch.object(
            service, "_call_openrouter_json",
            side_effect=[batch_tr, Exception("API down")],
        ):
            with pytest.raises(Exception, match="API down"):
                service.process_article(article)

        article.refresh_from_db()
        # Partial save: translations saved, but no summary/analysis
        assert article.title_es == "Titulo"
        assert article.ai_processed is False

    def test_raises_when_no_content_generated(self):
        """Si todas las llamadas retornan None/vacio, lanza NoContentError."""
        from apps.articles.models import Article

        article = Article.objects.create(
            title="Test", abstract_original="Abstract", language_original="en",
        )

        service = _make_service()

        # All batch calls return None (e.g. model unavailable, 429, timeouts)
        with patch.object(service, "_call_openrouter_json", return_value=None):
            with patch.object(service, "_translate", return_value=""):
                with patch.object(service, "_call_openrouter", return_value=None):
                    with pytest.raises(NoContentError):
                        service.process_article(article)

        article.refresh_from_db()
        assert article.ai_processed is False
        assert article.ai_summary == ""

    def test_skips_existing_fields(self):
        from apps.articles.models import Article

        article = Article.objects.create(
            title="Test",
            abstract_original="Abstract",
            language_original="en",
            title_es="Ya traducido",
            title_ru="Uzhe perevedeno",
            abstract_es="Ya existe",
            abstract_ru="Uzhe est",
            ai_summary="Existing summary",
            ai_summary_en="Existing summary EN",
            ai_analysis="Existing analysis",
            ai_analysis_en="Existing analysis EN",
        )

        service = _make_service()

        # Only batch_translate_sa should be called (step 3)
        sa_tr = {
            "ai_summary_es": "Resumen existente ES",
            "ai_summary_ru": "Sushchestvuyushchee rezyume",
            "ai_analysis_es": "Analisis existente ES",
            "ai_analysis_ru": "Sushchestvuyushchij analiz",
        }

        with patch.object(
            service, "_call_openrouter_json",
            return_value=sa_tr,
        ) as mock_json:
            result = service.process_article(article)

        article.refresh_from_db()
        assert article.ai_processed is True
        # Title/abstract translations were preserved
        assert article.title_es == "Ya traducido"
        # Existing summary preserved
        assert article.ai_summary == "Existing summary"
        # New SA translations applied
        assert article.ai_summary_es == "Resumen existente ES"


@pytest.mark.django_db
class TestForceReanalysis:
    """Test del flujo force=true (reset en la vista, re-process en servicio)."""

    def test_reprocesses_after_field_reset(self):
        """Simula el flujo de force=true: la vista resetea campos y llama process_article."""
        from apps.articles.models import Article

        article = Article.objects.create(
            title="Test",
            abstract_original="Abstract",
            language_original="en",
            ai_processed=True,
            ai_summary="Old summary",
            ai_summary_en="Old summary EN",
            ai_analysis="Old analysis",
            ai_analysis_en="Old analysis EN",
            title_es="Viejo",
            title_ru="Staryj",
        )

        # Simular lo que hace la vista con force=true
        for field in (
            "title_es", "title_en", "title_ru",
            "abstract_es", "abstract_en", "abstract_ru",
            "ai_summary", "ai_summary_es", "ai_summary_en", "ai_summary_ru",
            "ai_analysis", "ai_analysis_es", "ai_analysis_en", "ai_analysis_ru",
        ):
            setattr(article, field, "")
        article.ai_processed = False
        article.save()

        service = _make_service()
        batch_tr = {"title_es": "Nuevo", "title_ru": "Novyj"}
        sa = {"summary": "New summary", "analysis": "New analysis"}
        sa_tr = {
            "ai_summary_es": "Nuevo resumen",
            "ai_summary_ru": "Novoe rezyume",
            "ai_analysis_es": "Nuevo analisis",
            "ai_analysis_ru": "Novyj analiz",
        }

        with patch.object(
            service, "_call_openrouter_json",
            side_effect=[batch_tr, sa, sa_tr],
        ):
            service.process_article(article)

        article.refresh_from_db()
        assert article.ai_processed is True
        assert article.title_es == "Nuevo"
        assert article.ai_summary == "New summary"
        assert article.ai_analysis == "New analysis"
        assert article.ai_summary_es == "Nuevo resumen"


# ── Tests de deadline ────────────────────────────────────────────────


class TestDeadline:
    """Tests para el deadline global de _call_openrouter."""

    @patch("apps.agent.openrouter_service.time.monotonic")
    def test_raises_deadline_exceeded_when_time_runs_out(self, mock_monotonic):
        """Si el deadline se alcanza antes de la llamada, lanza DeadlineExceededError."""
        service = _make_service()
        # Simular que el tiempo ya se pasó
        mock_monotonic.side_effect = [0.0, 100.0]

        with pytest.raises(DeadlineExceededError):
            service._call_openrouter("test prompt")


# ── Tests de run_analysis (background task) ─────────────────────────


@pytest.mark.django_db
class TestRunAnalysis:
    """Tests para la función run_analysis (ejecutada por django-q2)."""

    def test_marks_processing_then_completed(self):
        from apps.articles.models import Article
        from apps.agent.services import run_analysis

        article = Article.objects.create(
            title="Test BG",
            abstract_original="Abstract for background test",
            language_original="en",
        )

        batch_tr = {"title_es": "Test BG ES", "title_ru": "Test BG RU"}
        sa = {"summary": "BG Summary", "analysis": "BG Analysis"}
        sa_tr = {
            "ai_summary_es": "Resumen BG",
            "ai_summary_ru": "Rezyume BG",
            "ai_analysis_es": "Análisis BG",
            "ai_analysis_ru": "Analiz BG",
        }

        with patch.multiple(
            "apps.agent.openrouter_service.settings",
            OPENROUTER_API_KEY="test-key",
            OPENROUTER_MODEL="test-model",
            LLM_PROVIDER="openrouter",
        ):
            with patch(
                "apps.agent.openrouter_service.OpenRouterService._call_openrouter_json",
                side_effect=[batch_tr, sa, sa_tr],
            ):
                result = run_analysis(article.pk)

        article.refresh_from_db()
        assert article.ai_processed is True
        assert article.ai_processing is False
        assert article.ai_error == ""
        assert "successfully" in result

    def test_saves_error_on_failure(self):
        from apps.articles.models import Article
        from apps.agent.services import run_analysis

        article = Article.objects.create(
            title="Test Fail",
            abstract_original="Abstract",
            language_original="en",
        )

        with patch.multiple(
            "apps.agent.openrouter_service.settings",
            OPENROUTER_API_KEY="test-key",
            OPENROUTER_MODEL="test-model",
            LLM_PROVIDER="openrouter",
        ):
            with patch(
                "apps.agent.openrouter_service.OpenRouterService._call_openrouter_json",
                side_effect=RateLimitError("All models rate-limited"),
            ):
                result = run_analysis(article.pk)

        article.refresh_from_db()
        assert article.ai_processing is False
        assert article.ai_error_code == "rate_limited"
        assert "rate_limited" in result

    def test_not_found_article(self):
        from apps.agent.services import run_analysis
        result = run_analysis(999999)
        assert "not found" in result


# ── Tests de endpoints analyze (202) y analyze-status ──────────────


@pytest.mark.django_db
class TestAnalyzeEndpoint:
    """Tests para los endpoints de análisis async."""

    def test_analyze_returns_202(self, api_client):
        from apps.articles.models import Article

        article = Article.objects.create(
            title="Test Async",
            abstract_original="Abstract",
            language_original="en",
        )

        with patch("django_q.tasks.async_task", return_value="fake-task-id"):
            response = api_client.post(f"/api/articles/{article.pk}/analyze/")

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "queued"
        assert data["article_id"] == article.pk

        # Article should now be marked as processing
        article.refresh_from_db()
        assert article.ai_processing is True

    def test_analyze_returns_202_when_already_processing(self, api_client):
        from apps.articles.models import Article

        article = Article.objects.create(
            title="Already Processing",
            abstract_original="Abstract",
            language_original="en",
            ai_processing=True,
        )

        response = api_client.post(f"/api/articles/{article.pk}/analyze/")
        assert response.status_code == 202
        assert response.json()["status"] == "processing"

    def test_analyze_status_idle(self, api_client):
        from apps.articles.models import Article

        article = Article.objects.create(
            title="Idle",
            abstract_original="Abstract",
            language_original="en",
        )

        response = api_client.get(f"/api/articles/{article.pk}/analyze-status/")
        assert response.status_code == 200
        assert response.json()["status"] == "idle"

    def test_analyze_status_completed(self, api_client):
        from apps.articles.models import Article

        article = Article.objects.create(
            title="Done",
            abstract_original="Abstract",
            language_original="en",
            ai_processed=True,
        )

        response = api_client.get(f"/api/articles/{article.pk}/analyze-status/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert "article" in data

    def test_analyze_status_failed(self, api_client):
        from apps.articles.models import Article

        article = Article.objects.create(
            title="Failed",
            abstract_original="Abstract",
            language_original="en",
            ai_error="Rate limited",
            ai_error_code="rate_limited",
        )

        response = api_client.get(f"/api/articles/{article.pk}/analyze-status/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["error_code"] == "rate_limited"

    def test_analyze_status_processing(self, api_client):
        from apps.articles.models import Article

        article = Article.objects.create(
            title="Processing",
            abstract_original="Abstract",
            language_original="en",
            ai_processing=True,
        )

        response = api_client.get(f"/api/articles/{article.pk}/analyze-status/")
        assert response.status_code == 200
        assert response.json()["status"] == "processing"
