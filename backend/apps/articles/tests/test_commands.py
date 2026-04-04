"""Tests del management command cleanup_stuck_articles."""
import pytest
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.utils import timezone

from apps.articles.models import Article


@pytest.mark.django_db
class TestCleanupStuckArticles:
    """Verifica que el cleanup resetea ai_processing y respeta --dry-run."""

    def _age_article(self, article, minutes):
        """Fuerza updated_at al pasado para simular antigüedad."""
        old = timezone.now() - timedelta(minutes=minutes)
        Article.objects.filter(pk=article.pk).update(updated_at=old)
        article.refresh_from_db()

    def test_resets_stuck_articles(self, article_factory):
        a1 = article_factory(ai_processing=True)
        a2 = article_factory(ai_processing=True)
        a3 = article_factory(ai_processing=False)
        # Envejecer 15 min para superar umbral default (10 min)
        self._age_article(a1, 15)
        self._age_article(a2, 15)

        out = StringIO()
        call_command("cleanup_stuck_articles", stdout=out)

        a1.refresh_from_db()
        a2.refresh_from_db()
        a3.refresh_from_db()

        assert a1.ai_processing is False
        assert a1.ai_error == "Análisis interrumpido (reinicio del servidor)"
        assert a1.ai_error_code == "interrupted"
        assert a2.ai_processing is False
        assert a3.ai_processing is False
        assert "2 artículo(s)" in out.getvalue()

    def test_skips_recent_processing(self, article_factory):
        """Artículos recientes (< umbral) no se tocan: podrían estar en curso."""
        recent = article_factory(ai_processing=True)
        # updated_at es ~now, así que con --minutes=10 no debe resetearse.

        out = StringIO()
        call_command("cleanup_stuck_articles", stdout=out)

        recent.refresh_from_db()
        assert recent.ai_processing is True
        assert "No hay artículos atascados" in out.getvalue()

    def test_minutes_zero_resets_all(self, article_factory):
        """--minutes=0 resetea todo sin importar antigüedad."""
        recent = article_factory(ai_processing=True)

        out = StringIO()
        call_command("cleanup_stuck_articles", "--minutes=0", stdout=out)

        recent.refresh_from_db()
        assert recent.ai_processing is False
        assert "1 artículo(s)" in out.getvalue()

    def test_no_stuck_articles(self):
        out = StringIO()
        call_command("cleanup_stuck_articles", stdout=out)
        assert "No hay artículos atascados" in out.getvalue()

    def test_dry_run_does_not_modify(self, article_factory):
        a = article_factory(ai_processing=True)
        self._age_article(a, 15)

        out = StringIO()
        call_command("cleanup_stuck_articles", "--dry-run", stdout=out)

        a.refresh_from_db()
        assert a.ai_processing is True  # No modificado
        assert "[dry-run]" in out.getvalue()
