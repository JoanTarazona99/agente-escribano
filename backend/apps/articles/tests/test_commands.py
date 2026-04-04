"""Tests del management command cleanup_stuck_articles."""
import pytest
from io import StringIO

from django.core.management import call_command

from apps.articles.models import Article


@pytest.mark.django_db
class TestCleanupStuckArticles:
    """Verifica que el cleanup resetea ai_processing y respeta --dry-run."""

    def test_resets_stuck_articles(self, article_factory):
        a1 = article_factory(ai_processing=True)
        a2 = article_factory(ai_processing=True)
        a3 = article_factory(ai_processing=False)

        out = StringIO()
        call_command("cleanup_stuck_articles", stdout=out)

        a1.refresh_from_db()
        a2.refresh_from_db()
        a3.refresh_from_db()

        assert a1.ai_processing is False
        assert a1.ai_error == "Análisis interrumpido (reinicio del servidor)"
        assert a1.ai_error_code == "timeout"
        assert a2.ai_processing is False
        assert a3.ai_processing is False
        assert "2 artículo(s)" in out.getvalue()

    def test_no_stuck_articles(self):
        out = StringIO()
        call_command("cleanup_stuck_articles", stdout=out)
        assert "No hay artículos atascados" in out.getvalue()

    def test_dry_run_does_not_modify(self, article_factory):
        a = article_factory(ai_processing=True)

        out = StringIO()
        call_command("cleanup_stuck_articles", "--dry-run", stdout=out)

        a.refresh_from_db()
        assert a.ai_processing is True  # No modificado
        assert "[dry-run]" in out.getvalue()
