"""Conector para arXiv.org — API Atom pública, sin credenciales requeridas."""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET

import httpx

from .base import ArticleData, BaseSearchConnector

ARXIV_API_URL = "https://export.arxiv.org/api/query"
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
}

# arXiv requiere mínimo 3 s entre peticiones; User-Agent recomendado
_RATE_LIMIT_DELAY = 3.0
HEADERS = {
    "User-Agent": (
        "AgenteEscribano/1.0 (research tool; contact: admin@example.com) "
        "httpx/0.28"
    )
}


class ArxivConnector(BaseSearchConnector):
    """
    Conector para arXiv usando la API Atom oficial.
    Docs: https://arxiv.org/help/api/user-manual
    """

    SOURCE_DB = "arxiv"

    def search(self, query: str, max_results: int = 50) -> list[ArticleData]:
        """
        Busca artículos en arXiv.

        La query se envía como `search_query=all:{query}`.
        httpx se encarga del URL-encoding; NO usar quote_plus aquí.
        """
        self.logger.info("arXiv search: %s (max=%d)", query, max_results)

        # Construimos la URL manualmente para evitar doble-encoding por httpx
        search_query = f"all:{query}"
        url = (
            f"{ARXIV_API_URL}"
            f"?search_query={search_query.replace(' ', '+')}"
            f"&start=0"
            f"&max_results={max_results}"
            f"&sortBy=relevance"
            f"&sortOrder=descending"
        )

        retries = 3
        for attempt in range(retries):
            try:
                with httpx.Client(timeout=30.0, headers=HEADERS) as client:
                    response = client.get(url)
                    if response.status_code == 429:
                        wait = _RATE_LIMIT_DELAY * (attempt + 2)
                        self.logger.warning("arXiv 429 rate-limit, esperando %.0fs…", wait)
                        time.sleep(wait)
                        continue
                    response.raise_for_status()
                    return self._parse_response(response.text)
            except httpx.HTTPError as exc:
                self.logger.error("arXiv HTTP error (intento %d): %s", attempt + 1, exc)
                if attempt < retries - 1:
                    time.sleep(_RATE_LIMIT_DELAY)

        return []

    def _parse_response(self, xml_text: str) -> list[ArticleData]:
        """Parsea la respuesta Atom XML de arXiv."""
        root = ET.fromstring(xml_text)
        articles: list[ArticleData] = []

        for entry in root.findall("atom:entry", NS):
            title_el = entry.find("atom:title", NS)
            summary_el = entry.find("atom:summary", NS)
            published_el = entry.find("atom:published", NS)
            id_el = entry.find("atom:id", NS)

            title = (title_el.text or "").strip().replace("\n", " ") if title_el is not None else ""
            abstract = (summary_el.text or "").strip() if summary_el is not None else ""
            arxiv_url = (id_el.text or "").strip() if id_el is not None else ""
            arxiv_id = arxiv_url.split("/abs/")[-1] if "/abs/" in arxiv_url else ""

            year: int | None = None
            if published_el is not None and published_el.text:
                try:
                    year = int(published_el.text[:4])
                except ValueError:
                    pass

            # Autores
            authors = ", ".join(
                (a.find("atom:name", NS).text or "").strip()
                for a in entry.findall("atom:author", NS)
                if a.find("atom:name", NS) is not None
            )

            # DOI (puede estar en link con title="doi")
            doi: str | None = None
            for link in entry.findall("atom:link", NS):
                if link.get("title") == "doi":
                    href = link.get("href", "")
                    doi = href.replace("https://doi.org/", "").replace("http://doi.org/", "") or None

            if not title:
                continue

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
                    language="en",
                )
            )

        self.logger.info("arXiv: %d artículos recuperados", len(articles))
        return articles
