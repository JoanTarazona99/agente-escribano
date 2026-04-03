"""Conector para arXiv.org — API Atom pública, sin credenciales requeridas."""
from __future__ import annotations

import re
import time
from xml.etree import ElementTree as ET

import httpx

from .base import ArticleData, BaseSearchConnector

# API Atom oficial — funciona en cualquier entorno (no requiere navegador).
ARXIV_API_URL = "https://export.arxiv.org/api/query"

# Namespaces XML de la respuesta Atom de arXiv
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}

# arXiv pide esperar >= 3 s entre requests
_RATE_LIMIT_DELAY = 3.0


class ArxivConnector(BaseSearchConnector):
    """
    Conector para arXiv usando la API Atom pública.
    Docs: https://info.arxiv.org/help/api/index.html
    """

    SOURCE_DB = "arxiv"

    def search(self, query: str, max_results: int = 50) -> list[ArticleData]:
        """
        Busca artículos en arXiv vía la API Atom.

        La query se envía directamente como `search_query=all:{query}`.
        """
        self.logger.info("arXiv API search: %s (max=%d)", query, max_results)

        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": min(max_results, 200),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }

        retries = 3
        for attempt in range(retries):
            try:
                with httpx.Client(timeout=30.0) as client:
                    resp = client.get(ARXIV_API_URL, params=params)
                    if resp.status_code == 429:
                        self.logger.warning("arXiv 429 rate-limited, esperando %ss", _RATE_LIMIT_DELAY)
                        time.sleep(_RATE_LIMIT_DELAY)
                        continue
                    resp.raise_for_status()
                    return self._parse_atom(resp.text)[:max_results]
            except httpx.HTTPStatusError as exc:
                self.logger.error("arXiv HTTP error (intento %d): %s", attempt + 1, exc)
                if attempt < retries - 1:
                    time.sleep(_RATE_LIMIT_DELAY)
            except Exception as exc:
                self.logger.error("arXiv error (intento %d): %s", attempt + 1, exc)
                if attempt < retries - 1:
                    time.sleep(_RATE_LIMIT_DELAY)

        return []

    def _parse_atom(self, xml_text: str) -> list[ArticleData]:
        """Parsea la respuesta Atom XML de la API de arXiv."""
        root = ET.fromstring(xml_text)
        articles: list[ArticleData] = []

        for entry in root.findall("atom:entry", NS):
            # Título
            title_el = entry.find("atom:title", NS)
            title = (title_el.text or "").strip() if title_el is not None else ""
            # Limpiar saltos de línea en el título
            title = re.sub(r"\s+", " ", title)
            if not title:
                continue

            # Autores
            authors = ", ".join(
                (a.find("atom:name", NS).text or "").strip()
                for a in entry.findall("atom:author", NS)
                if a.find("atom:name", NS) is not None and a.find("atom:name", NS).text
            )

            # Abstract
            summary_el = entry.find("atom:summary", NS)
            abstract = (summary_el.text or "").strip() if summary_el is not None else ""
            abstract = re.sub(r"\s+", " ", abstract)

            # URL y arXiv ID
            arxiv_url = ""
            arxiv_id = ""
            for link in entry.findall("atom:link", NS):
                if link.get("type") == "text/html" or link.get("rel") == "alternate":
                    arxiv_url = link.get("href", "")
                    break
            id_el = entry.find("atom:id", NS)
            if id_el is not None and id_el.text:
                # Formato: http://arxiv.org/abs/2301.12345v1
                arxiv_id = id_el.text.strip().split("/abs/")[-1].split("v")[0]
                if not arxiv_url:
                    arxiv_url = f"https://arxiv.org/abs/{arxiv_id}"

            # Año (de published)
            year: int | None = None
            published_el = entry.find("atom:published", NS)
            if published_el is not None and published_el.text:
                try:
                    year = int(published_el.text[:4])
                except (ValueError, IndexError):
                    pass

            # DOI
            doi: str | None = None
            doi_el = entry.find("arxiv:doi", NS)
            if doi_el is not None and doi_el.text:
                doi = doi_el.text.strip() or None

            # Categorías / keywords
            categories = ", ".join(
                c.get("term", "")
                for c in entry.findall("atom:category", NS)
                if c.get("term")
            )

            # Journal ref
            journal = ""
            journal_el = entry.find("arxiv:journal_ref", NS)
            if journal_el is not None and journal_el.text:
                journal = journal_el.text.strip()

            articles.append(
                ArticleData(
                    title=title,
                    authors=authors,
                    abstract=abstract,
                    year=year,
                    doi=doi,
                    url=arxiv_url,
                    source_db=self.SOURCE_DB,
                    source_id=arxiv_id,
                    journal=journal,
                    keywords=categories,
                    language="en",
                )
            )

        self.logger.info("arXiv API: %d artículos recuperados", len(articles))
        return articles
