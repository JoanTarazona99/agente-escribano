"""
Orquestador de búsqueda: coordina todos los conectores activos,
deduplica por DOI y persiste los artículos encontrados.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from apps.articles.models import Article, SearchJob, SourceDatabase

from .connectors import (
    ArxivConnector,
    ArticleData,
    ElibraryConnector,
    ScopusConnector,
    WOSConnector,
)

logger = logging.getLogger(__name__)

DEFAULT_QUERY = (
    "dissociation recombination water molecules electromembrane systems "
    "ion-exchange membrane bipolar membrane transport"
)

CONNECTOR_MAP = {
    SourceDatabase.ARXIV: ArxivConnector,
    SourceDatabase.ELIBRARY: ElibraryConnector,
    SourceDatabase.SCOPUS: ScopusConnector,
    SourceDatabase.WOS: WOSConnector,
}


class SearchOrchestrator:
    """
    Ejecuta la búsqueda en todas (o algunas) fuentes académicas y
    persiste los resultados en la base de datos.
    """

    def __init__(self, sources: list[str] | None = None, max_per_source: int = 50) -> None:
        """
        Args:
            sources: Lista de valores SourceDatabase a consultar.
                     Si es None, se usan todas las fuentes disponibles.
            max_per_source: Máximo de resultados por fuente.
        """
        self.sources = sources or list(SourceDatabase.values)
        self.max_per_source = max_per_source

    def run(self, query: str, job: SearchJob | None = None, notebook=None) -> dict[str, int]:
        """
        Ejecuta la búsqueda completa.

        Args:
            query: Términos de búsqueda.
            job: SearchJob asociado para actualizar el estado (opcional).
            notebook: Notebook al que agregar automáticamente los artículos (opcional).

        Returns:
            Diccionario {source: count_saved}
        """
        if job:
            job.status = SearchJob.Status.RUNNING
            job.save(update_fields=["status"])

        results: dict[str, int] = {}
        total_found = 0
        total_saved = 0
        all_articles: list[Article] = []  # acumula instancias para asociar al job

        for source in self.sources:
            connector_class = CONNECTOR_MAP.get(source)
            if connector_class is None:
                logger.warning("No existe conector para fuente: %s", source)
                continue

            connector = connector_class()

            if not connector.is_available():
                logger.info("Conector %s no disponible (faltan credenciales), omitiendo.", source)
                results[source] = 0
                continue

            try:
                articles_data = connector.search(query, max_results=self.max_per_source)
            except NotImplementedError as exc:
                logger.warning("Conector %s: %s", source, exc)
                results[source] = 0
                continue
            except Exception as exc:
                logger.error("Error en conector %s: %s", source, exc)
                results[source] = 0
                continue

            saved_instances, count = self._save_articles(articles_data)
            all_articles.extend(saved_instances)
            results[source] = count
            total_found += len(articles_data)
            total_saved += count
            logger.info("Fuente %s: %d encontrados, %d guardados.", source, len(articles_data), count)

        if job:
            job.status = SearchJob.Status.COMPLETED
            job.total_found = total_found
            job.total_saved = total_saved
            job.finished_at = datetime.now(tz=timezone.utc)
            job.save(update_fields=["status", "total_found", "total_saved", "finished_at"])
            if all_articles:
                job.articles.set(all_articles)

        # Auto-agregar artículos al cuaderno si se proporcionó
        if notebook and all_articles:
            notebook.articles.add(*all_articles)

        return results

    def _save_articles(self, articles_data: list[ArticleData]) -> tuple[list[Article], int]:
        """
        Persiste la lista de ArticleData. Devuelve (instancias, nuevas_creadas).
        Deduplica por DOI o por source_db+source_id.
        """
        instances: list[Article] = []
        saved = 0
        for data in articles_data:
            try:
                if data.doi:
                    obj, created = Article.objects.update_or_create(
                        doi=data.doi,
                        defaults=self._to_model_fields(data),
                    )
                elif data.source_id:
                    obj, created = Article.objects.get_or_create(
                        source_db=data.source_db,
                        source_id=data.source_id,
                        defaults=self._to_model_fields(data),
                    )
                else:
                    obj = Article.objects.create(**self._to_model_fields(data))
                    created = True
                instances.append(obj)
                if created:
                    saved += 1
            except Exception as exc:
                logger.error("Error guardando artículo '%s': %s", data.title[:60], exc)

        return instances, saved

    @staticmethod
    def _to_model_fields(data: ArticleData) -> dict:
        fields = {
            "title": data.title,
            "authors": data.authors,
            "abstract_original": data.abstract,
            "year": data.year,
            "url": data.url,
            "source_db": data.source_db,
            "source_id": data.source_id,
            "journal": data.journal,
            "keywords": data.keywords,
            "language_original": data.language,
        }
        if data.doi:
            fields["doi"] = data.doi
        return fields
