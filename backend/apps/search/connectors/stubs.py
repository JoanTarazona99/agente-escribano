"""
Conector para Web of Science Starter API (Clarivate).
Requiere WOS_API_KEY en settings / .env

Documentación: https://developer.clarivate.com/apis/wos-starter
Endpoint: GET https://api.clarivate.com/apis/wos-starter/v1/documents
Autenticación: header X-ApiKey
Plan: Free trial (Starter), límites en el portal de Clarivate.
"""
from __future__ import annotations

import time

import httpx
from django.conf import settings

from .base import ArticleData, BaseSearchConnector

# WOS Starter API base URL
WOS_BASE_URL = "https://api.clarivate.com/apis/wos-starter/v1"

# Rate-limit delay entre reintentos (segundos)
_RATE_LIMIT_DELAY = 2.0


class WOSConnector(BaseSearchConnector):
    """
    Conector para Web of Science Starter API (Clarivate).
    Requiere WOS_API_KEY configurada en .env

    Campos disponibles en la respuesta:
    - Title, Authors, DOI, UID (Accession Number)
    - Source (journal), Publication Date, Keywords
    - Times Cited, Document Type
    """

    SOURCE_DB = "wos"

    def is_available(self) -> bool:
        return bool(getattr(settings, "WOS_API_KEY", ""))

    def search(self, query: str, max_results: int = 50) -> list[ArticleData]:
        """
        Busca documentos en Web of Science Starter API.

        Args:
            query: Términos de búsqueda (se envían al campo 'q')
            max_results: Máximo de resultados (API permite hasta 50 por request)

        Returns:
            Lista de ArticleData
        """
        api_key = getattr(settings, "WOS_API_KEY", "")
        if not api_key:
            raise ValueError(
                "WOSConnector requiere WOS_API_KEY configurada en .env. "
                "Consulta https://developer.clarivate.com/ para obtener credenciales."
            )

        limit = min(max_results, 50)  # Starter API: max 50 per page

        headers = {
            "X-ApiKey": api_key,
            "Accept": "application/json",
        }

        params = {
            "q": query,
            "limit": limit,
            "page": 1,
        }

        # Proxy para desarrollo local (VPN); vacío en producción.
        proxy = getattr(settings, "HTTP_PROXY", "") or None
        timeout = httpx.Timeout(connect=15.0, read=30.0, write=10.0, pool=5.0)

        retries = 3
        last_error = ""

        for attempt in range(retries):
            try:
                with httpx.Client(timeout=timeout, proxy=proxy) as client:
                    resp = client.get(
                        f"{WOS_BASE_URL}/documents",
                        headers=headers,
                        params=params,
                    )

                    if resp.status_code == 429:
                        self.logger.warning(
                            "WOS 429 rate-limited (intento %d/%d), esperando %ss",
                            attempt + 1, retries, _RATE_LIMIT_DELAY,
                        )
                        time.sleep(_RATE_LIMIT_DELAY)
                        continue

                    if resp.status_code == 401:
                        raise ValueError("WOS API Key inválida o expirada")
                    if resp.status_code == 403:
                        raise ValueError(
                            "WOS: acceso denegado. Verifica permisos de la API key "
                            "y que el plan Starter esté activo."
                        )

                    resp.raise_for_status()
                    data = resp.json()
                    return self._parse_response(data)

            except httpx.HTTPStatusError as exc:
                last_error = f"HTTP {exc.response.status_code}"
                self.logger.error(
                    "WOS HTTP error (intento %d/%d): %s",
                    attempt + 1, retries, exc,
                )
                if attempt < retries - 1:
                    time.sleep(_RATE_LIMIT_DELAY)
            except httpx.TimeoutException as exc:
                last_error = f"Timeout: {exc}"
                self.logger.error(
                    "WOS timeout (intento %d/%d): %s",
                    attempt + 1, retries, exc,
                )
                if attempt < retries - 1:
                    time.sleep(_RATE_LIMIT_DELAY * 2)
            except ValueError:
                raise  # Propagar errores de auth
            except Exception as exc:
                last_error = str(exc)
                self.logger.error(
                    "WOS error (intento %d/%d): %s",
                    attempt + 1, retries, exc,
                )
                if attempt < retries - 1:
                    time.sleep(_RATE_LIMIT_DELAY)

        self.logger.error(
            "WOS: todos los intentos fallaron para query=%r. Último error: %s",
            query, last_error,
        )
        return []

    def _parse_response(self, data: dict) -> list[ArticleData]:
        """Parsea la respuesta JSON de WOS Starter API."""
        articles: list[ArticleData] = []
        hits = data.get("hits", [])

        if not hits:
            self.logger.info("WOS: 0 resultados encontrados")
            return articles

        for hit in hits:
            try:
                title = self._get_title(hit)
                if not title:
                    continue

                uid = hit.get("uid", "")
                doi = self._get_doi(hit)
                url = self._build_url(uid, doi)

                articles.append(
                    ArticleData(
                        title=title,
                        authors=self._get_authors(hit),
                        abstract="",  # Starter API no incluye abstracts
                        year=self._get_year(hit),
                        doi=doi,
                        url=url,
                        source_db=self.SOURCE_DB,
                        source_id=uid,
                        journal=self._get_source(hit),
                        keywords=self._get_keywords(hit),
                        language="en",
                    )
                )
            except Exception as e:
                self.logger.warning("Error parseando entrada WOS: %s", e)
                continue

        self.logger.info("WOS: %d artículos recuperados", len(articles))
        return articles

    @staticmethod
    def _get_title(hit: dict) -> str:
        """Extrae el título del documento."""
        title = hit.get("title", "")
        if isinstance(title, str):
            return title.strip()
        # Algunas respuestas usan formato de lista
        if isinstance(title, list) and title:
            return str(title[0]).strip()
        return ""

    @staticmethod
    def _get_authors(hit: dict) -> str:
        """Extrae autores como string separado por comas."""
        names = hit.get("names", {})
        if isinstance(names, dict):
            authors_list = names.get("authors", [])
            if isinstance(authors_list, list):
                return ", ".join(
                    a.get("displayName", a.get("wosStandard", ""))
                    for a in authors_list
                    if isinstance(a, dict)
                )
        return ""

    @staticmethod
    def _get_year(hit: dict) -> int | None:
        """Extrae el año de publicación."""
        # Campo directo
        year = hit.get("publicationDate", {})
        if isinstance(year, dict):
            y = year.get("year")
            if y:
                try:
                    return int(y)
                except (ValueError, TypeError):
                    pass

        # Fallback: campo source.publishYear
        source = hit.get("source", {})
        if isinstance(source, dict):
            py = source.get("publishYear")
            if py:
                try:
                    return int(py)
                except (ValueError, TypeError):
                    pass

        return None

    @staticmethod
    def _get_doi(hit: dict) -> str | None:
        """Extrae el DOI."""
        identifiers = hit.get("identifiers", {})
        if isinstance(identifiers, dict):
            doi = identifiers.get("doi", "")
            if doi:
                return doi.strip()

        # Fallback
        doi = hit.get("doi", "")
        if doi:
            return doi.strip()
        return None

    @staticmethod
    def _get_source(hit: dict) -> str:
        """Extrae nombre de la revista/fuente."""
        source = hit.get("source", {})
        if isinstance(source, dict):
            name = source.get("sourceTitle", "")
            if name:
                return name.strip()
        return ""

    @staticmethod
    def _get_keywords(hit: dict) -> str:
        """Extrae keywords del documento."""
        kw = hit.get("keywords", {})
        if isinstance(kw, dict):
            author_kw = kw.get("authorKeywords", [])
            if isinstance(author_kw, list):
                return ", ".join(str(k) for k in author_kw if k)
        return ""

    @staticmethod
    def _build_url(uid: str, doi: str | None) -> str:
        """Construye la URL más útil para el artículo."""
        if doi:
            return f"https://doi.org/{doi}"
        if uid:
            return f"https://www.webofscience.com/wos/woscc/full-record/{uid}"
        return ""

