"""Vistas DRF para artículos científicos."""
import logging
from datetime import timedelta
from django.utils import timezone
import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser

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

    def perform_update(self, serializer):
        """Guardar y asegurar que el objeto refrescado se use en la respuesta."""
        instance = serializer.save()
        instance.refresh_from_db()

    def update(self, request, *args, **kwargs):
        """Sobrescribe para devolver el detalle completo tras actualización."""
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(ArticleDetailSerializer(instance).data)


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

        if article.ai_processing:
            stale_cutoff = timezone.now() - timedelta(minutes=5)
            if article.updated_at < stale_cutoff:
                logger.warning(
                    "Articulo %s atascado (>5 min). Auto-reset y re-encolar.",
                    article.pk,
                )
                Article.objects.filter(pk=article.pk).update(
                    ai_processing=False,
                    ai_error="",
                    ai_error_code="",
                )
                article.refresh_from_db()
            else:
                return Response(
                    {"status": "processing", "detail": "El analisis ya esta en curso."},
                    status=status.HTTP_202_ACCEPTED,
                )

        article.ai_processing = True
        article.ai_error = ""
        article.ai_error_code = ""
        article.save(update_fields=["ai_processing", "ai_error", "ai_error_code"])

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
            stale_cutoff = timezone.now() - timedelta(minutes=20)
            if article.updated_at < stale_cutoff:
                logger.warning(
                    "Artículo %s atascado en ai_processing=True desde %s. Auto-reset.",
                    article.pk, article.updated_at,
                )
                Article.objects.filter(pk=article.pk).update(
                    ai_processing=False,
                    ai_error="Análisis interrumpido (timeout del worker)",
                    ai_error_code="timeout",
                )
                article.refresh_from_db()
                return Response({
                    "status": "failed",
                    "error": article.ai_error,
                    "error_code": "timeout",
                })
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


    @extend_schema(
        summary="Subir archivo al cuaderno",
        description=(
            "Sube un archivo (PDF, TXT, DOCX) y lo añade como fuente al cuaderno. "
            "El texto se extrae automáticamente y queda disponible para análisis IA, "
            "igual que los artículos obtenidos por búsqueda."
        ),
        request={"multipart/form-data": {"type": "object", "properties": {"file": {"type": "string", "format": "binary"}}}},
        responses={201: ArticleDetailSerializer},
    )
    @action(detail=True, methods=["post"], url_path="upload-file", parser_classes=[MultiPartParser, FormParser])
    def upload_file(self, request: Request, pk=None) -> Response:
        """Sube un archivo y lo convierte en un artículo en el cuaderno."""
        notebook = self.get_object()
        file_obj = request.FILES.get("file")

        if not file_obj:
            return Response(
                {"detail": "No se proporcionó ningún archivo."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validar tamaño (máximo 20 MB)
        MAX_FILE_SIZE = 20 * 1024 * 1024
        if file_obj.size and file_obj.size > MAX_FILE_SIZE:
            return Response(
                {"detail": "El archivo excede el tamaño máximo de 20 MB."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        filename = file_obj.name
        file_ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        SUPPORTED_EXTENSIONS = {"pdf", "txt", "doc", "docx", "md", "tex", "rtf"}

        if file_ext not in SUPPORTED_EXTENSIONS:
            return Response(
                {"detail": f"Tipo de archivo '.{file_ext}' no soportado. Usa: {', '.join(sorted(SUPPORTED_EXTENSIONS))}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        content = self._extract_text(file_obj, file_ext, filename)

        if not content or content.startswith("[Error"):
            logger.warning(f"No se pudo extraer texto del archivo {filename}")
            # Aún así crear el artículo para que el usuario pueda renombrarlo/editarlo
            if not content:
                content = ""

        # Generar título legible a partir del nombre de archivo
        title = filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").strip()

        # Crear el artículo: abstract_original = primeros 2000 chars, full_text = todo
        abstract_preview = content[:2000].strip() if content else ""

        article = Article.objects.create(
            title=title,
            authors="",
            abstract_original=abstract_preview,
            full_text=content,
            original_filename=filename,
            source_db="file",
            source_id=f"file:{filename}",
            language_original=self._detect_language(content[:500]) if content else "",
        )

        # Añadir al cuaderno
        notebook.articles.add(article)

        serializer = ArticleDetailSerializer(article)
        logger.info(f"📄 Archivo '{filename}' subido como fuente #{article.pk} al notebook #{notebook.pk} ({len(content)} chars)")
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @staticmethod
    def _extract_text(file_obj, file_ext: str, filename: str) -> str:
        """Extrae texto de un archivo según su extensión."""
        import io

        try:
            if file_ext == "pdf":
                try:
                    import PyPDF2
                    pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_obj.read()))
                    pages = []
                    for page in pdf_reader.pages:
                        text = page.extract_text()
                        if text:
                            pages.append(text)
                    return "\n\n".join(pages)
                except ImportError:
                    logger.error("PyPDF2 no está instalado")
                    return "[Error: PyPDF2 no instalado — ejecuta pip install PyPDF2]"

            elif file_ext in ("txt", "md", "tex", "rtf"):
                raw = file_obj.read()
                # Intentar UTF-8, luego latin-1 como fallback
                for encoding in ("utf-8", "latin-1", "cp1252"):
                    try:
                        return raw.decode(encoding)
                    except (UnicodeDecodeError, AttributeError):
                        continue
                return raw.decode("utf-8", errors="ignore")

            elif file_ext in ("doc", "docx"):
                try:
                    from docx import Document
                    doc = Document(io.BytesIO(file_obj.read()))
                    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
                    return "\n\n".join(paragraphs)
                except ImportError:
                    logger.error("python-docx no está instalado")
                    return "[Error: python-docx no instalado — ejecuta pip install python-docx]"

            else:
                return f"[Formato .{file_ext} no soportado]"

        except Exception as e:
            logger.error(f"Error al procesar archivo {filename}: {e}")
            return f"[Error al extraer texto: {str(e)}]"

    @staticmethod
    def _detect_language(text: str) -> str:
        """Detección simple de idioma basada en caracteres."""
        if not text:
            return ""
        # Contar caracteres cirílicos vs latinos
        cyrillic = sum(1 for c in text if "\u0400" <= c <= "\u04ff")
        latin = sum(1 for c in text if "a" <= c.lower() <= "z")
        # Palabras frecuentes en español
        es_markers = sum(1 for w in ("de", "en", "la", "el", "los", "las", "del", "una", "por", "con")
                         if f" {w} " in text.lower())
        if cyrillic > latin * 0.3:
            return "ru"
        if es_markers > 5:
            return "es"
        return "en"
