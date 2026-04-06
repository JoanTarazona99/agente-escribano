"""Tests de los endpoints DRF de artículos."""
import pytest
from rest_framework import status

from apps.articles.models import Article


@pytest.mark.django_db
class TestArticleListAPI:
    def test_list_returns_200(self, api_client):
        response = api_client.get("/api/articles/")
        assert response.status_code == status.HTTP_200_OK

    def test_list_paginated_structure(self, api_client):
        response = api_client.get("/api/articles/")
        data = response.json()
        assert "count" in data
        assert "results" in data

    def test_list_filters_by_source_db(self, api_client, article_factory):
        article_factory(source_db="arxiv", title="arXiv article")
        article_factory(source_db="elibrary", title="eLIBRARY article")
        response = api_client.get("/api/articles/?source_db=arxiv")
        data = response.json()
        assert all(a["source_db"] == "arxiv" for a in data["results"])

    def test_list_search_filter(self, api_client, article_factory):
        article_factory(title="Water dissociation unique term xyzabc")
        response = api_client.get("/api/articles/?search=xyzabc")
        assert response.json()["count"] >= 1

    def test_list_serializer_fields(self, api_client, article_factory):
        article_factory()
        response = api_client.get("/api/articles/")
        article = response.json()["results"][0]
        assert "id" in article
        assert "title" in article
        assert "source_db" in article
        assert "doi_url" in article
        assert "has_doi" in article
        # El detalle NO debe estar en el listado
        assert "ai_summary" not in article
        assert "ai_analysis" not in article


@pytest.mark.django_db
class TestArticleDetailAPI:
    def test_detail_returns_full_fields(self, api_client, article_factory):
        article = article_factory(ai_summary="Test summary", ai_processed=True)
        response = api_client.get(f"/api/articles/{article.pk}/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["ai_summary"] == "Test summary"
        assert data["ai_processed"] is True

    def test_detail_404_for_missing(self, api_client):
        response = api_client.get("/api/articles/99999/")
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestArticleAnalyzeAPI:
    def test_analyze_enqueues_task_returns_202(self, api_client, article_factory, mocker):
        """El endpoint /analyze/ debe encolar una tarea y devolver 202."""
        article = article_factory()
        mocker.patch("django_q.tasks.async_task", return_value="fake-task-id")
        response = api_client.post(f"/api/articles/{article.pk}/analyze/")
        assert response.status_code == status.HTTP_202_ACCEPTED
        data = response.json()
        assert data["status"] == "queued"
        assert data["article_id"] == article.pk

    def test_analyze_already_processing_returns_202(self, api_client, article_factory):
        """Si ya está procesando, devuelve 202 con status=processing."""
        article = article_factory(ai_processing=True)
        response = api_client.post(f"/api/articles/{article.pk}/analyze/")
        assert response.status_code == status.HTTP_202_ACCEPTED
        assert response.json()["status"] == "processing"

    def test_analyze_force_resets_ai_fields(self, api_client, article_factory, mocker):
        """force=true encola la tarea con force=True para resetear campos IA."""
        article = article_factory(
            ai_processed=True, ai_summary="Old", ai_analysis="Old",
        )
        mock_async = mocker.patch("django_q.tasks.async_task", return_value="fake-task-id")
        response = api_client.post(f"/api/articles/{article.pk}/analyze/?force=true")
        assert response.status_code == status.HTTP_202_ACCEPTED
        # Verify force=True is passed to the background task
        mock_async.assert_called_once()
        args = mock_async.call_args
        assert args[0][2] is True  # third positional arg is force=True


@pytest.mark.django_db
class TestArticleUpdateAPI:
    def test_update_title_and_type_returns_200(self, api_client, article_factory):
        """El endpoint PATCH /articles/{id}/ debe permitir actualizar el título y el tipo."""
        article = article_factory(title="Old Title", article_type="unknown")
        payload = {"title": "New Title", "article_type": "theoretical"}
        response = api_client.patch(f"/api/articles/{article.pk}/", payload)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["title"] == "New Title"
        assert data["article_type"] == "theoretical"

        # Verificar persistencia en base de datos
        article.refresh_from_db()
        assert article.title == "New Title"
        assert article.article_type == "theoretical"

    def test_update_forbidden_fields_ignored(self, api_client, article_factory):
        """Campos como ai_processed o source_db no deben ser actualizables vía API."""
        article = article_factory(source_db="arxiv", ai_processed=False)
        payload = {"source_db": "scopus", "ai_processed": True}
        response = api_client.patch(f"/api/articles/{article.pk}/", payload)
        assert response.status_code == status.HTTP_200_OK

        article.refresh_from_db()
        assert article.source_db == "arxiv"  # No cambió
        assert article.ai_processed is False  # No cambió
