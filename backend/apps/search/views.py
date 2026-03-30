"""Vistas DRF para lanzar búsquedas de artículos."""
from __future__ import annotations

import threading

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.articles.models import SearchJob
from apps.articles.serializers import SearchJobSerializer

from .orchestrator import DEFAULT_QUERY, SearchOrchestrator


class SearchRateThrottle(AnonRateThrottle):
    """Limita búsquedas a 10/min para evitar abuso."""
    rate = "10/min"


class SearchView(APIView):
    """
    Lanza una búsqueda asíncrona en todas las fuentes académicas configuradas.
    """

    throttle_classes = [SearchRateThrottle]

    @extend_schema(
        summary="Lanzar búsqueda de artículos",
        description=(
            "Inicia una búsqueda en arXiv, eLIBRARY, Scopus y Web of Science. "
            "La búsqueda se ejecuta en segundo plano. Devuelve el ID del job "
            "para consultar el estado en GET /api/jobs/{id}/."
        ),
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Términos de búsqueda. Si se omite, usa la query por defecto sobre ЭМС.",
                        "example": "water dissociation recombination electromembrane",
                    },
                    "sources": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["arxiv", "elibrary", "scopus", "wos"]},
                        "description": "Fuentes a consultar (por defecto: todas).",
                    },
                    "max_per_source": {
                        "type": "integer",
                        "description": "Máximo de resultados por fuente (por defecto: 50).",
                        "default": 50,
                    },
                },
            }
        },
        responses={202: SearchJobSerializer},
    )
    def post(self, request: Request) -> Response:
        query = request.data.get("query", DEFAULT_QUERY)
        sources = request.data.get("sources", None)
        max_per_source = int(request.data.get("max_per_source", 50))
        notebook_id = request.data.get("notebook_id", None)

        # Resolver notebook si se proporcionó
        from apps.articles.models import Notebook
        notebook = None
        if notebook_id:
            try:
                notebook = Notebook.objects.get(pk=notebook_id)
            except Notebook.DoesNotExist:
                pass

        # Crear job de seguimiento
        job = SearchJob.objects.create(
            query=query,
            sources=",".join(sources) if sources else "arxiv,elibrary,scopus,wos",
            notebook=notebook,
        )

        # Ejecutar en hilo separado para no bloquear la respuesta HTTP
        def run_search() -> None:
            orchestrator = SearchOrchestrator(sources=sources, max_per_source=max_per_source)
            try:
                orchestrator.run(query=query, job=job, notebook=notebook)
            except Exception as exc:
                job.status = SearchJob.Status.FAILED
                job.error_message = str(exc)
                job.save(update_fields=["status", "error_message"])

        thread = threading.Thread(target=run_search, daemon=True)
        thread.start()

        serializer = SearchJobSerializer(job)
        return Response(serializer.data, status=status.HTTP_202_ACCEPTED)
