"""Conector para arXiv.org — búsqueda HTML pública, sin credenciales requeridas."""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from bs4 import BeautifulSoup

from .base import ArticleData, BaseSearchConnector

ARXIV_SEARCH_URL = "https://arxiv.org/search/"
PROJECT_ROOT = Path(__file__).resolve().parents[4]
FRONTEND_ROOT = PROJECT_ROOT / "frontend"

# arXiv puede rechazar scraping agresivo; mantenemos una pausa corta entre reintentos.
_RATE_LIMIT_DELAY = 3.0

class ArxivConnector(BaseSearchConnector):
    """
    Conector para arXiv usando la página HTML pública de búsqueda.
    Docs: https://arxiv.org/search/
    """

    SOURCE_DB = "arxiv"

    def search(self, query: str, max_results: int = 50) -> list[ArticleData]:
        """
        Busca artículos en arXiv.

        La query se envía como búsqueda HTML normal en `search/?query=...`.
        """
        self.logger.info("arXiv search: %s (max=%d)", query, max_results)

        params = {
            "query": query,
            "searchtype": "all",
            "size": 50,
        }

        retries = 3
        for attempt in range(retries):
            try:
                html = self._fetch_html(params)
                if html:
                    return self._parse_response(html)[:max_results]
            except Exception as exc:
                self.logger.error("arXiv HTML error (intento %d): %s", attempt + 1, exc)
                if attempt < retries - 1:
                    time.sleep(_RATE_LIMIT_DELAY)

        return []

    def _fetch_html(self, params: dict[str, object]) -> str:
        """Obtiene el HTML de búsqueda de arXiv usando Playwright de Node."""
        query = str(params.get("query", ""))
        size = int(params.get("size", 50))
        url = f"{ARXIV_SEARCH_URL}?query={query.replace(' ', '+')}&searchtype=all&size={size}"

        script = f"""
const {{ chromium }} = require('playwright');
(async() => {{
  const browser = await chromium.launch({{ headless: true }});
  const page = await browser.newPage();
  await page.goto({json.dumps(url)}, {{ waitUntil: 'domcontentloaded', timeout: 60000 }});
  await page.waitForSelector('li.arxiv-result', {{ timeout: 30000 }}).catch(() => null);
  process.stdout.write(await page.content());
  await browser.close();
}})().catch(err => {{
  console.error(err);
  process.exit(1);
}});
"""

        completed = subprocess.run(
            ["node", "-e", script],
            cwd=FRONTEND_ROOT,
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        if completed.returncode != 0:
            stderr = (completed.stderr or completed.stdout or "").strip()
            raise RuntimeError(stderr or f"Playwright node exited with code {completed.returncode}")

        return completed.stdout

    def _parse_response(self, html_text: str) -> list[ArticleData]:
        """Parsea la respuesta HTML de arXiv."""
        soup = BeautifulSoup(html_text, "html.parser")
        articles: list[ArticleData] = []

        for entry in soup.select("li.arxiv-result"):
            title_link = entry.select_one("p.title a")
            title_el = entry.select_one("p.title")
            authors_el = entry.select_one("p.authors")
            abstract_el = entry.select_one("span.abstract-full") or entry.select_one("span.abstract-short")
            meta_el = entry.select_one("p.is-size-7")

            title = ""
            arxiv_url = ""
            arxiv_id = ""
            if title_el:
                title = title_el.get_text(" ", strip=True)
                if title.lower().startswith("title:"):
                    title = title[len("title:"):].strip()

            if title_link:
                arxiv_url = title_link.get("href", "").strip()
                if "/abs/" in arxiv_url:
                    arxiv_id = arxiv_url.split("/abs/")[-1].split("v")[0]

            if not arxiv_url:
                abs_link = entry.select_one("p.list-title a[href*='/abs/']") or entry.select_one("a[href*='/abs/']")
                if abs_link:
                    arxiv_url = abs_link.get("href", "").strip()
                    if "/abs/" in arxiv_url:
                        arxiv_id = arxiv_url.split("/abs/")[-1].split("v")[0]

            if not title and title_link:
                title = title_link.get_text(" ", strip=True)

            if not title:
                continue

            authors = ""
            if authors_el:
                authors = ", ".join(
                    a.get_text(" ", strip=True)
                    for a in authors_el.select("a")
                    if a.get_text(strip=True)
                )

            abstract = ""
            if abstract_el:
                abstract = abstract_el.get_text(" ", strip=True)
                if abstract.lower().startswith("abstract:"):
                    abstract = abstract[len("abstract:"):].strip()

            year: int | None = None
            if meta_el:
                meta_text = meta_el.get_text(" ", strip=True)
                # Example: "Submitted 31 March, 2026; v1 submitted..."
                for token in ("2026", "2025", "2024", "2023", "2022", "2021", "2020"):
                    if token in meta_text:
                        try:
                            year = int(token)
                            break
                        except ValueError:
                            pass

            doi: str | None = None
            doi_link = entry.select_one("a[href*='doi.org']")
            if doi_link:
                href = doi_link.get("href", "")
                doi = href.replace("https://doi.org/", "").replace("http://doi.org/", "") or None

            keywords = ""
            keywords_el = entry.select_one("p.tags")
            if keywords_el:
                keywords = keywords_el.get_text(", ", strip=True)

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
                    keywords=keywords,
                    language="en",
                )
            )

        self.logger.info("arXiv: %d artículos recuperados", len(articles))
        return articles
