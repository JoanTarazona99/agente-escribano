"""
Conectores de búsqueda para fuentes académicas.

Jerarquía:
  BaseSearchConnector (abstracto)
  ├── ArxivConnector       — API pública, sin credenciales
  ├── ElibraryConnector    — scraping httpx + BeautifulSoup4
  ├── ScopusConnector      — Elsevier API (requiere SCOPUS_API_KEY)
  └── WOSConnector         — WOS Starter API (requiere WOS_API_KEY)
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ArticleData:
    """DTO con los datos de un artículo recuperado de cualquier fuente."""

    title: str
    authors: str = ""
    abstract: str = ""
    year: int | None = None
    doi: str | None = None
    url: str = ""
    source_db: str = "unknown"
    source_id: str = ""
    journal: str = ""
    keywords: str = ""
    language: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


class BaseSearchConnector(ABC):
    """Interfaz base para todos los conectores de búsqueda académica."""

    SOURCE_DB: str = "unknown"

    def __init__(self) -> None:
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    def search(self, query: str, max_results: int = 50) -> list[ArticleData]:
        """
        Ejecuta la búsqueda y devuelve una lista de ArticleData.

        Args:
            query: Términos de búsqueda.
            max_results: Límite de resultados a recuperar.

        Returns:
            Lista de ArticleData normalizados.
        """
        ...

    def is_available(self) -> bool:
        """Indica si el conector está listo para usarse (credenciales, etc.)."""
        return True
