"""
Conector para Scopus (Elsevier API).
Requiere SCOPUS_API_KEY en settings / .env

Documentación API: https://dev.elsevier.com/sc_apis.html
"""
from __future__ import annotations

import logging

import httpx
from django.conf import settings

from .base import ArticleData, BaseSearchConnector

logger = logging.getLogger(__name__)

SCOPUS_BASE_URL = "https://api.elsevier.com/content/search/scopus"


class ScopusConnector(BaseSearchConnector):
    """
    Conector para Scopus (Elsevier API).
    Requiere SCOPUS_API_KEY configurada en .env
    """

    SOURCE_DB = "scopus"

    def is_available(self) -> bool:
        """Verifica si la API key de Scopus está disponible."""
        return bool(getattr(settings, "SCOPUS_API_KEY", ""))

    def search(self, query: str, max_results: int = 50) -> list[ArticleData]:
        """
        Busca en Scopus usando la API de Elsevier.

        Args:
            query: Términos de búsqueda
            max_results: Máximo resultados a retornar (max 200 por request de Scopus)

        Returns:
            Lista de ArticleData
        """
        api_key = getattr(settings, "SCOPUS_API_KEY", "")
        if not api_key:
            raise ValueError(
                "ScopusConnector requiere SCOPUS_API_KEY configurada en .env. "
                "Consulta https://dev.elsevier.com/ para obtener credenciales."
            )

        # Scopus REST API limit: 200 resultados por request
        limit = min(max_results, 200)

        params = {
            "query": query,
            "count": limit,
            "start": 0,
            "sort": "plf-f(pubyear,2020)",  # Sort por año reciente primero
        }

        headers = {
            "Accept": "application/json",
            "X-ELS-APIKey": api_key,
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.get(SCOPUS_BASE_URL, params=params, headers=headers)

                # Manejo de errores específicos
                if response.status_code == 401:
                    raise ValueError("Scopus API Key inválida o expirada")
                elif response.status_code == 429:
                    raise ValueError("Scopus: rate limit alcanzado, intenta más tarde")
                elif response.status_code == 403:
                    raise ValueError("Scopus: acceso denegado. Verifica permisos de la API key")

                response.raise_for_status()

                data = response.json()
                results: list[ArticleData] = []

                # Parsear resultados de Scopus
                entries = data.get("search-results", {}).get("entry", [])
                if not entries:
                    logger.info("Scopus: %d resultados encontrados", 0)
                    return results

                for entry in entries:
                    try:
                        article = ArticleData(
                            title=entry.get("dc:title", "").strip(),
                            authors=self._parse_authors(entry.get("dc:creator", "")),
                            abstract=entry.get("dc:description", "").strip() or "",
                            year=self._parse_year(entry.get("prism:coverDate", "")),
                            source_db="scopus",
                            source_id=entry.get("eid", ""),  # Elsevier ID
                            doi=entry.get("prism:doi", "").strip() or None,
                            journal=entry.get("prism:publicationName", "").strip(),
                            url=self._parse_url(entry),
                            language="en",  # Scopus es principalmente en inglés
                            keywords="",  # Scopus no devuelve keywords en REST básico
                        )
                        if article.title:  # Solo agregar si tiene título
                            results.append(article)
                    except Exception as e:
                        logger.warning("Error parseando entrada Scopus: %s", e)
                        continue

                logger.info(
                    "Scopus: búsqueda completada. %d resultados encontrados",
                    len(results),
                )
                return results

        except httpx.HTTPError as e:
            raise ValueError(f"Scopus API error: {str(e)}")
        except ValueError:
            raise  # Re-raise nuestros propios ValueErrors
        except Exception as e:
            logger.error("Error inesperado en Scopus connector: %s", e)
            raise ValueError(f"Scopus búsqueda falló: {str(e)}")

    @staticmethod
    def _parse_authors(creator_str: str) -> str:
        """
        Parsear string de autores de Scopus.
        Scopus devuelve generalmente un string con autores separados.
        """
        if not creator_str:
            return ""

        # Intentar separar por delimitadores comunes
        authors = []
        for author in creator_str.split(";"):
            author = author.strip()
            if author:
                authors.append(author)

        return ", ".join(authors) if authors else creator_str

    @staticmethod
    def _parse_year(date_str: str) -> int | None:
        """Extraer año de la fecha de cobertura (formato YYYY-MM-DD)."""
        if not date_str:
            return None
        try:
            return int(date_str[:4])
        except (ValueError, IndexError):
            return None

    @staticmethod
    def _parse_url(entry: dict) -> str:
        """Construir URL del artículo en Scopus."""
        eid = entry.get("eid", "")
        if eid:
            # URL estándar de Scopus record display
            return f"https://www.scopus.com/record/display.uri?eid={eid}"

        # Fallback: intentar usar campo link si existe
        links = entry.get("link", [])
        for link in links:
            if isinstance(link, dict) and link.get("@ref") == "scopus":
                return link.get("@href", "")

        return ""
