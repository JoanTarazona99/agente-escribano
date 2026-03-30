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
        summary="Analizar artículo con IA",
        description=(
            "Envía el artículo al servicio Ollama para generar traducción, "
            "resumen y análisis. El proceso se ejecuta en segundo plano. "
            "Consulte GET /api/articles/{id}/ para ver el resultado."
        ),
        responses={202: ArticleDetailSerializer},
    )
    @action(detail=True, methods=["post"], url_path="analyze")
    def analyze(self, request: Request, pk: int = None) -> Response:
        """Ejecuta el análisis IA de forma síncrona y devuelve el artículo procesado."""
        from apps.agent.services import OllamaService

        article = self.get_object()

        try:
            service = OllamaService()
            service.process_article(article)
            article.refresh_from_db()
        except Exception as exc:
            logger.error(
                "Error en análisis IA del artículo %s: %s",
                article.pk, exc, exc_info=True,
            )
            return Response(
                {"detail": f"Error en análisis IA: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        serializer = ArticleDetailSerializer(article)
        return Response(serializer.data, status=status.HTTP_200_OK)


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

