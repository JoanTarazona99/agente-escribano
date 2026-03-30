"""Tests del modelo Article y SearchJob."""
import pytest
from django.core.exceptions import ValidationError

from apps.articles.models import Article, ArticleType, SearchJob, SourceDatabase


@pytest.mark.django_db
class TestArticleModel:
    def test_str_includes_source_db_uppercase(self):
        article = Article.objects.create(
            title="Water dissociation in bipolar membranes",
            source_db=SourceDatabase.ARXIV,
        )
        assert "[ARXIV]" in str(article)
        assert "Water dissociation" in str(article)

    def test_has_doi_property_true(self):
        article = Article(doi="10.1016/j.memsci.2023.121234")
        assert article.has_doi is True

    def test_has_doi_property_false_when_none(self):
        article = Article(doi=None)
        assert article.has_doi is False

    def test_doi_url_property(self):
        doi = "10.1016/j.memsci.2023.121234"
        article = Article(doi=doi)
        assert article.doi_url == f"https://doi.org/{doi}"

    def test_doi_url_empty_when_no_doi(self):
        article = Article(doi=None)
        assert article.doi_url == ""

    def test_doi_uniqueness(self, article_factory):
        doi = "10.1234/test.unique.doi"
        article_factory(doi=doi)
        with pytest.raises(Exception):  # IntegrityError
            article_factory(doi=doi, title="Duplicate")

    def test_optional_fields_default_empty_string(self):
        article = Article.objects.create(title="Minimal Article")
        assert article.authors == ""
        assert article.abstract_original == ""
        assert article.keywords == ""
        assert article.ai_summary == ""
        assert article.ai_processed is False

    def test_source_db_choices(self):
        for value in ["scopus", "wos", "arxiv", "elibrary", "unknown"]:
            assert value in SourceDatabase.values

    def test_article_type_choices(self):
        for value in ["theoretical", "experimental", "review", "mixed", "unknown"]:
            assert value in ArticleType.values


@pytest.mark.django_db
class TestSearchJobModel:
    def test_str_includes_status_and_query(self):
        job = SearchJob.objects.create(query="water dissociation EMS")
        assert "pending" in str(job)
        assert "water dissociation" in str(job)

    def test_default_status_is_pending(self):
        job = SearchJob.objects.create(query="test query")
        assert job.status == SearchJob.Status.PENDING

    def test_total_counters_default_zero(self):
        job = SearchJob.objects.create(query="test")
        assert job.total_found == 0
        assert job.total_saved == 0
