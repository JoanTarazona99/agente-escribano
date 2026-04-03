"""Tests del OllamaService con mock del cliente ollama."""
import pytest
from unittest.mock import MagicMock, patch, call

from apps.agent.services import OllamaService


def make_ollama_response(text: str) -> dict:
    return {"message": {"content": text}}


class TestOllamaService:
    def _make_service(self, mock_client):
        """Helper para instanciar OllamaService con cliente mockeado."""
        with patch("ollama.Client", return_value=mock_client):
            return OllamaService()

    def test_translate_to_es(self):
        mock_client = MagicMock()
        mock_client.chat.return_value = make_ollama_response("Disociación del agua en membranas bipolares.")
        service = self._make_service(mock_client)
        result = service.translate("Water dissociation in bipolar membranes.", target_lang="es")
        assert result == "Disociación del agua en membranas bipolares."
        mock_client.chat.assert_called_once()

    def test_translate_to_en(self):
        mock_client = MagicMock()
        mock_client.chat.return_value = make_ollama_response("Water dissociation study.")
        service = self._make_service(mock_client)
        result = service.translate("Изучение диссоциации воды.", target_lang="en")
        assert result == "Water dissociation study."

    def test_translate_returns_empty_for_empty_input(self):
        mock_client = MagicMock()
        service = self._make_service(mock_client)
        result = service.translate("", target_lang="es")
        assert result == ""
        mock_client.chat.assert_not_called()

    def test_translate_raises_for_unsupported_lang(self):
        mock_client = MagicMock()
        service = self._make_service(mock_client)
        with pytest.raises(ValueError, match="fr"):
            service.translate("text", target_lang="fr")

    def test_summarize_returns_summary(self):
        mock_client = MagicMock()
        mock_client.chat.return_value = make_ollama_response("Resumen: estudio de disociación.")
        service = self._make_service(mock_client)
        result = service.summarize("Title", "Abstract text")
        assert "Resumen" in result

    def test_analyze_returns_analysis(self):
        mock_client = MagicMock()
        mock_client.chat.return_value = make_ollama_response("1. TIPO: Experimental\n2. METODOLOGÍA: Voltametría")
        service = self._make_service(mock_client)
        result = service.analyze("Title", "Abstract")
        assert "Experimental" in result

    @pytest.mark.django_db
    def test_process_article_updates_ai_fields(self):
        from apps.articles.models import Article
        article = Article.objects.create(
            title="Water recombination study",
            abstract_original="Study of water recombination in EMS systems.",
            language_original="en",
        )

        mock_client = MagicMock()
        mock_client.chat.side_effect = [
            make_ollama_response("Estudio de recombinación"),      # translate abstract ES
            make_ollama_response("Estudio título ES"),             # translate title ES
            make_ollama_response("Исследование рекомбинации"),     # translate abstract RU
            make_ollama_response("Исследование заголовок RU"),     # translate title RU
            make_ollama_response("Summary of recombination."),     # summarize (ru)
            make_ollama_response("1. TIPO: Experimental"),         # analyze (ru)
            make_ollama_response("Resumen ES"),                    # translate summary to ES
            make_ollama_response("Summary EN"),                    # translate summary to EN
            make_ollama_response("Análisis ES"),                   # translate analysis to ES
            make_ollama_response("Analysis EN"),                   # translate analysis to EN
        ]

        with patch("ollama.Client", return_value=mock_client):
            service = OllamaService()
            service.process_article(article)

        article.refresh_from_db()
        assert article.ai_processed is True
        assert article.ai_summary != ""
        assert article.ai_analysis != ""

    @pytest.mark.django_db
    def test_process_article_propagates_ollama_error(self):
        from apps.articles.models import Article
        article = Article.objects.create(
            title="Test", abstract_original="Test abstract", language_original="ru"
        )
        mock_client = MagicMock()
        mock_client.chat.side_effect = ConnectionError("Ollama unreachable")

        with patch("ollama.Client", return_value=mock_client):
            service = OllamaService()
            with pytest.raises(ConnectionError):
                service.process_article(article)
