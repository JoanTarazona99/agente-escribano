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
    def test_analyze_calls_ollama_service(self, api_client, article_factory, mocker):
        """El endpoint /analyze/ debe delegar al OllamaService y devolver 202."""
        article = article_factory()
        mock_process = mocker.patch(
            "apps.agent.services.OllamaService.process_article",
            return_value=None,
        )
        response = api_client.post(f"/api/articles/{article.pk}/analyze/")
        assert response.status_code == status.HTTP_202_ACCEPTED
        mock_process.assert_called_once_with(article)

    def test_analyze_returns_503_on_ollama_error(self, api_client, article_factory, mocker):
        article = article_factory()
        mocker.patch(
            "apps.agent.services.OllamaService.process_article",
            side_effect=ConnectionError("Ollama no disponible"),
        )
        response = api_client.post(f"/api/articles/{article.pk}/analyze/")
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
