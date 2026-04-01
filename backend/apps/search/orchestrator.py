"""
Orquestador de búsqueda: coordina todos los conectores activos,
deduplica por DOI y persiste los artículos encontrados.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from apps.articles.models import Article, SearchJob, SourceDatabase, Notebook

from .connectors import (
    ArxivConnector,
    ArticleData,
    ElibraryConnector,
    ScopusConnector,
    WOSConnector,
)

logger = logging.getLogger(__name__)
LOG_PATH = Path(__file__).resolve().parent.parent.parent / "orchestrator_debug.log"

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
                try:
                    with open(LOG_PATH, "a", encoding="utf-8") as fh:
                        fh.write(
                            f"SOURCE {source} FOUND {len(articles_data)} JOB {getattr(job, 'pk', 'unknown')}\n"
                        )
                except Exception:
                    logger.exception("No se pudo escribir debug tras búsqueda")
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
            # contabilizamos los guardados explícitamente; para evitar discrepancias
            # calculamos el total encontrado tras el guardado usando las instancias
            # retornadas por _save_articles (incluye artículos existentes y nuevos).
            total_saved += count
            logger.info("Fuente %s: %d procesados, %d guardados.", source, len(saved_instances), count)

        # Recalcular totales a partir de las instancias realmente asociadas
        total_found = len(all_articles)
        if job:
            job.status = SearchJob.Status.COMPLETED
            job.total_found = total_found
            job.total_saved = total_saved
            job.finished_at = datetime.now(tz=timezone.utc)
            job.save(update_fields=["status", "total_found", "total_saved", "finished_at"])
            if all_articles:
                job.articles.set(all_articles)

        # Auto-agregar artículos al cuaderno si se proporcionó.
        # Re-obtenemos la instancia de `Notebook` desde la base de datos
        # dentro del hilo de fondo para evitar problemas de compartir
        # instancias de modelo entre hilos.
        if notebook and all_articles:
            try:
                if hasattr(notebook, "pk"):
                    nb = Notebook.objects.get(pk=notebook.pk)
                else:
                    nb = Notebook.objects.get(pk=int(notebook))
                # Debugging: write pre/post counts to a file to inspect threaded behavior
                try:
                    with open(LOG_PATH, "a", encoding="utf-8") as fh:
                        fh.write(f"JOB {getattr(job, 'pk', 'unknown')} NOTEBOOK {nb.pk} PRE_COUNT {nb.articles.count()} ADDING {len(all_articles)}\n")
                except Exception:
                    logger.exception("No se pudo escribir debug antes de add()")

                nb.articles.add(*all_articles)

                try:
                    with open(LOG_PATH, "a", encoding="utf-8") as fh:
                        fh.write(f"JOB {getattr(job, 'pk', 'unknown')} NOTEBOOK {nb.pk} POST_COUNT {nb.articles.count()}\n")
                except Exception:
                    logger.exception("No se pudo escribir debug despues de add()")
            except Notebook.DoesNotExist:
                logger.warning("Notebook %s no existe al intentar agregar artículos.", getattr(notebook, "pk", notebook))
            except Exception as exc:
                logger.exception("Error añadiendo artículos al cuaderno: %s", exc)
                try:
                    with open(LOG_PATH, "a", encoding="utf-8") as fh:
                        fh.write(f"JOB {getattr(job, 'pk', 'unknown')} NOTEBOOK {getattr(notebook,'pk',notebook)} EXC {exc}\n")
                except Exception:
                    logger.exception("No se pudo escribir debug en excepción")

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
                    obj, created = Article.objects.update_or_create(
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
                try:
                    with open(LOG_PATH, "a", encoding="utf-8") as fh:
                        fh.write(f"ERROR SAVING ARTICLE {data.title[:200]} EXC {exc}\n")
                except Exception:
                    logger.exception("No se pudo escribir debug de guardado")

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
