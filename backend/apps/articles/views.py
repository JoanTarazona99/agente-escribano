"""Vistas DRF para artículos científicos."""
import logging

import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from .models import Article, SearchJob, Notebook
from .serializers import (
    ArticleDetailSerializer,
    ArticleListSerializer,
    ArticleUpdateSerializer,
    SearchJobSerializer,
    NotebookListSerializer,
    NotebookDetailSerializer,
    NotebookUpdateSerializer,
)

logger = logging.getLogger(__name__)


class ArticleFilter(django_filters.FilterSet):
    """Filtros para la lista de artículos."""
    job = django_filters.NumberFilter(
        field_name="search_jobs",
        lookup_expr="exact",
        label="ID del SearchJob",
    )
    searchjob = django_filters.NumberFilter(
        field_name="search_jobs",
        lookup_expr="exact",
        label="Alias legado de job",
    )
    notebook = django_filters.NumberFilter(
        field_name="notebooks",
        lookup_expr="exact",
        label="ID del Notebook",
    )

    class Meta:
        model = Article
        fields = ["source_db", "article_type", "year", "ai_processed"]


@extend_schema_view(
    list=extend_schema(
        summary="Listar artículos",
        description="Devuelve la lista paginada de artículos con filtros opcionales.",
        parameters=[
            OpenApiParameter("source_db", description="Filtrar por fuente (arxiv, scopus, wos, elibrary)"),
            OpenApiParameter("article_type", description="Filtrar por tipo (theoretical, experimental, review, mixed)"),
            OpenApiParameter("year", description="Filtrar por año"),
            OpenApiParameter("ai_processed", description="Filtrar por procesamiento IA (true/false)"),
            OpenApiParameter("search", description="Búsqueda de texto en título, autores y abstract"),
        ],
    ),
    retrieve=extend_schema(summary="Detalle de artículo"),
    partial_update=extend_schema(summary="Actualizar campos de artículo"),
    destroy=extend_schema(summary="Eliminar artículo"),
)
class ArticleViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    ViewSet de solo lectura/actualización para artículos.
    La creación se realiza exclusivamente a través del agente de búsqueda.
    """

    queryset = Article.objects.all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ArticleFilter
    search_fields = ["title", "authors", "abstract_original", "keywords"]
    ordering_fields = ["year", "created_at", "title"]
    ordering = ["-year"]

    def get_serializer_class(self):
        if self.action == "list":
            return ArticleListSerializer
        if self.action in ("update", "partial_update"):
            return ArticleUpdateSerializer
        return ArticleDetailSerializer

    @extend_schema(
        summary="Analizar artículo con IA (background)",
        description=(
            "Encola el artículo para análisis IA en background (django-q2). "
            "Retorna 202 Accepted con el estado de la tarea.\n\n"
            "Pasar `?force=true` para regenerar campos IA aunque ya existan."
        ),
        parameters=[
            OpenApiParameter(
                "force", type=bool, location=OpenApiParameter.QUERY,
                description="Forzar re-análisis borrando campos IA previos.",
            ),
        ],
        responses={202: dict},
    )
    @action(detail=True, methods=["post"], url_path="analyze")
    def analyze(self, request: Request, pk: int = None) -> Response:
        """Encola el análisis IA en background y retorna 202."""
        from django_q.tasks import async_task

        article = self.get_object()
        force = request.query_params.get("force", "").lower() == "true"

        # Si ya está en proceso, no encolar de nuevo
        if article.ai_processing:
            return Response(
                {"status": "processing", "detail": "El análisis ya está en curso."},
                status=status.HTTP_202_ACCEPTED,
            )

        # Marcar como en cola inmediatamente para que el frontend lo detecte
        article.ai_processing = True
        article.ai_error = ""
        article.ai_error_code = ""
        article.save(update_fields=["ai_processing", "ai_error", "ai_error_code"])

        # Encolar tarea en background
        task_id = async_task(
            "apps.agent.services.run_analysis",
            article.pk,
            force,
            task_name=f"analyze-{article.pk}",
        )

        logger.info(
            "📋 Análisis encolado para artículo %s (task_id=%s, force=%s)",
            article.pk, task_id, force,
        )

        return Response(
            {
                "status": "queued",
                "task_id": str(task_id) if task_id else None,
                "article_id": article.pk,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @extend_schema(
        summary="Estado del análisis IA",
        description=(
            "Consulta el estado del análisis IA de un artículo.\n\n"
            "Posibles estados: queued, processing, completed, failed."
        ),
        responses={200: dict},
    )
    @action(detail=True, methods=["get"], url_path="analyze-status")
    def analyze_status(self, request: Request, pk: int = None) -> Response:
        """Devuelve el estado del análisis IA del artículo."""
        article = self.get_object()

        if article.ai_processing:
            return Response({"status": "processing"})

        if article.ai_error:
            return Response({
                "status": "failed",
                "error": article.ai_error,
                "error_code": article.ai_error_code or "unknown",
            })

        if article.ai_processed:
            serializer = ArticleDetailSerializer(article)
            return Response({
                "status": "completed",
                "article": serializer.data,
            })

        return Response({"status": "idle"})


class SearchJobViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Consultar el estado de los trabajos de búsqueda lanzados."""

    queryset = SearchJob.objects.all()
    serializer_class = SearchJobSerializer


@extend_schema_view(
    list=extend_schema(
        summary="Listar cuadernos",
        description="Devuelve la lista de todos los cuadernos del usuario.",
    ),
    create=extend_schema(
        summary="Crear cuaderno",
        description="Crea un nuevo cuaderno vacío.",
        request=NotebookUpdateSerializer,
        responses={201: NotebookDetailSerializer},
    ),
    retrieve=extend_schema(
        summary="Detalle de cuaderno",
        description="Obtiene el detalle completo de un cuaderno con sus artículos.",
    ),
    update=extend_schema(
        summary="Actualizar cuaderno",
        request=NotebookUpdateSerializer,
        responses={200: NotebookDetailSerializer},
    ),
    partial_update=extend_schema(
        summary="Actualización parcial de cuaderno",
        request=NotebookUpdateSerializer,
        responses={200: NotebookDetailSerializer},
    ),
    destroy=extend_schema(
        summary="Eliminar cuaderno",
        responses={204: None},
    ),
)
class NotebookViewSet(viewsets.ModelViewSet):
    """CRUD completo para cuadernos (notebooks)."""

    queryset = Notebook.objects.all()
    ordering = ["-created_at"]

    def get_serializer_class(self):
        if self.action == "list":
            return NotebookListSerializer
        elif self.action in ("update", "partial_update"):
            return NotebookUpdateSerializer
        else:
            return NotebookDetailSerializer

    @extend_schema(
        summary="Agregar artículo al cuaderno",
        description="Añade un artículo existente al cuaderno por su ID.",
        request=None,
        responses={200: NotebookDetailSerializer},
    )
    @action(detail=True, methods=["post"], url_path="add-article/(?P<article_id>[0-9]+)")
    def add_article(self, request: Request, pk=None, article_id=None) -> Response:
        notebook = self.get_object()
        try:
            article = Article.objects.get(pk=article_id)
        except Article.DoesNotExist:
            return Response(
                {"detail": "Artículo no encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )
        notebook.articles.add(article)
        serializer = NotebookDetailSerializer(notebook)
        return Response(serializer.data)

    @extend_schema(
        summary="Quitar artículo del cuaderno",
        description="Elimina un artículo del cuaderno (no borra el artículo).",
        request=None,
        responses={200: NotebookDetailSerializer},
    )
    @action(detail=True, methods=["post"], url_path="remove-article/(?P<article_id>[0-9]+)")
    def remove_article(self, request: Request, pk=None, article_id=None) -> Response:
        notebook = self.get_object()
        try:
            article = Article.objects.get(pk=article_id)
        except Article.DoesNotExist:
            return Response(
                {"detail": "Artículo no encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )
        notebook.articles.remove(article)
        serializer = NotebookDetailSerializer(notebook)
        return Response(serializer.data)

