"""
Fixtures globales de pytest para el backend.
DJANGO_SETTINGS_MODULE se configura en pyproject.toml → config.settings.local
"""
import pytest
from rest_framework.test import APIClient


@pytest.fixture
def api_client() -> APIClient:
    """Cliente DRF sin autenticar."""
    return APIClient()


@pytest.fixture
def article_factory():
    """Factory simple para crear artículos en tests."""
    from apps.articles.models import Article

    def _make(**kwargs) -> Article:
        defaults = {
            "title": "Test Article about Water Dissociation in EMS",
            "authors": "Ivanov, A.B.; Petrov, C.D.",
            "year": 2023,
            "source_db": "arxiv",
            "abstract_original": "Study of water dissociation in bipolar membranes.",
            "language_original": "en",
        }
        defaults.update(kwargs)
        return Article.objects.create(**defaults)

    return _make
