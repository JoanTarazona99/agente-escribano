"""
Modelos de la app articles.
Almacena artículos científicos sobre disociación/recombinación de H₂O en ЭМС.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _


class SourceDatabase(models.TextChoices):
    SCOPUS = "scopus", _("Scopus")
    WOS = "wos", _("Web of Science")
    ARXIV = "arxiv", _("arXiv")
    ELIBRARY = "elibrary", _("eLIBRARY")
    FILE = "file", _("Archivo local")
    UNKNOWN = "unknown", _("Desconocido")


class ArticleType(models.TextChoices):
    THEORETICAL = "theoretical", _("Teórico")
    EXPERIMENTAL = "experimental", _("Experimental")
    REVIEW = "review", _("Revisión / Survey")
    MIXED = "mixed", _("Teórico-Experimental")
    UNKNOWN = "unknown", _("No determinado")


class Article(models.Model):
    """
    Artículo científico recuperado por el agente de búsqueda.
    """

    # ─── Metadatos principales ────────────────────────────
    title = models.TextField(_("Título"), blank=False)
    authors = models.TextField(_("Autores"), blank=True, default="")
    year = models.IntegerField(_("Año de publicación"), null=True, blank=True)
    journal = models.CharField(_("Revista / Conferencia"), max_length=512, blank=True, default="")
    doi = models.CharField(
        _("DOI"),
        max_length=512,
        unique=True,
        null=True,
        blank=True,
        help_text="Identificador de objeto digital (puede ser nulo si no está disponible).",
    )
    url = models.URLField(_("URL"), max_length=2048, blank=True, default="")

    # ─── Fuente de datos ──────────────────────────────────
    source_db = models.CharField(
        _("Base de datos fuente"),
        max_length=20,
        choices=SourceDatabase.choices,
        default=SourceDatabase.UNKNOWN,
    )
    source_id = models.CharField(
        _("ID en la fuente"),
        max_length=256,
        blank=True,
        default="",
        help_text="ID interno del artículo en la base de datos de origen.",
    )

    # ─── Contenido original ───────────────────────────────
    abstract_original = models.TextField(
        _("Abstract original"),
        blank=True,
        default="",
        help_text="Texto del abstract en el idioma original del artículo.",
    )
    language_original = models.CharField(
        _("Idioma original"),
        max_length=10,
        blank=True,
        default="",
        help_text="Código ISO 639-1 del idioma original (ej: ru, en).",
    )
    keywords = models.TextField(
        _("Palabras clave"),
        blank=True,
        default="",
        help_text="Palabras clave separadas por comas.",
    )
    full_text = models.TextField(
        _("Texto completo"),
        blank=True,
        default="",
        help_text="Texto completo extraído del archivo subido (PDF, TXT, DOCX).",
    )
    original_filename = models.CharField(
        _("Nombre del archivo original"),
        max_length=512,
        blank=True,
        default="",
        help_text="Nombre del archivo subido por el usuario.",
    )

    # ─── Clasificación ────────────────────────────────────
    article_type = models.CharField(
        _("Tipo de artículo"),
        max_length=20,
        choices=ArticleType.choices,
        default=ArticleType.UNKNOWN,
    )

    # ─── Traducciones generadas por IA ───────────────────
    title_es = models.TextField(_("Título en español"), blank=True, default="")
    title_en = models.TextField(_("Título en inglés"), blank=True, default="")
    title_ru = models.TextField(_("Título en ruso"), blank=True, default="")
    abstract_es = models.TextField(_("Abstract en español"), blank=True, default="")
    abstract_en = models.TextField(_("Abstract en inglés"), blank=True, default="")
    abstract_ru = models.TextField(_("Abstract en ruso"), blank=True, default="")

    # ─── Análisis generado por IA (multilingüe) ──────────
    ai_summary = models.TextField(
        _("Resumen IA (legacy)"),
        blank=True,
        default="",
        help_text="Resumen IA principal — campo legacy, usar ai_summary_*.",
    )
    ai_summary_es = models.TextField(_("Resumen IA (ES)"), blank=True, default="")
    ai_summary_en = models.TextField(_("Resumen IA (EN)"), blank=True, default="")
    ai_summary_ru = models.TextField(_("Resumen IA (RU)"), blank=True, default="")

    ai_analysis = models.TextField(
        _("Análisis IA (legacy)"),
        blank=True,
        default="",
        help_text="Análisis IA principal — campo legacy, usar ai_analysis_*.",
    )
    ai_analysis_es = models.TextField(_("Análisis IA (ES)"), blank=True, default="")
    ai_analysis_en = models.TextField(_("Análisis IA (EN)"), blank=True, default="")
    ai_analysis_ru = models.TextField(_("Análisis IA (RU)"), blank=True, default="")

    ai_processed = models.BooleanField(
        _("Procesado por IA"),
        default=False,
        help_text="Indica si el artículo ha sido analizado por Ollama.",
    )
    ai_processing = models.BooleanField(
        _("Análisis en curso"),
        default=False,
        help_text="Indica que el artículo está siendo analizado en background.",
    )
    ai_error = models.TextField(
        _("Último error de análisis IA"),
        blank=True,
        default="",
        help_text="Mensaje del último error ocurrido durante el análisis IA.",
    )
    ai_error_code = models.CharField(
        _("Código de error IA"),
        max_length=30,
        blank=True,
        default="",
        help_text="Código tipificado: rate_limited, auth_error, model_unavailable, timeout, no_content, unknown.",
    )

    # ─── Timestamps ───────────────────────────────────────
    created_at = models.DateTimeField(_("Fecha de alta"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Última actualización"), auto_now=True)

    class Meta:
        verbose_name = _("Artículo")
        verbose_name_plural = _("Artículos")
        ordering = ["-year", "-created_at"]
        indexes = [
            models.Index(fields=["source_db"]),
            models.Index(fields=["year"]),
            models.Index(fields=["article_type"]),
            models.Index(fields=["ai_processed"]),
        ]

    def __str__(self) -> str:
        return f"[{self.source_db.upper()}] {self.title[:80]}"

    @property
    def has_doi(self) -> bool:
        return bool(self.doi)

    @property
    def doi_url(self) -> str:
        """URL completa del DOI en doi.org."""
        if self.doi:
            return f"https://doi.org/{self.doi}"
        return ""


class SearchJob(models.Model):
    """Registro de trabajos de búsqueda lanzados por el agente."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Pendiente")
        RUNNING = "running", _("En ejecución")
        COMPLETED = "completed", _("Completado")
        FAILED = "failed", _("Fallido")

    query = models.TextField(_("Consulta de búsqueda"))
    sources = models.CharField(
        _("Fuentes buscadas"),
        max_length=256,
        default="arxiv,elibrary,scopus,wos",
    )
    status = models.CharField(
        _("Estado"),
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    total_found = models.IntegerField(_("Total encontrados"), default=0)
    total_saved = models.IntegerField(_("Total guardados/actualizados"), default=0)
    error_message = models.TextField(_("Mensaje de error"), blank=True, default="")
    started_at = models.DateTimeField(_("Inicio"), auto_now_add=True)
    finished_at = models.DateTimeField(_("Fin"), null=True, blank=True)
    notebook = models.ForeignKey(
        "Notebook",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="search_jobs",
        verbose_name=_("Cuaderno asociado"),
    )
    articles = models.ManyToManyField(
        "Article",
        blank=True,
        related_name="search_jobs",
        verbose_name=_("Artículos encontrados"),
    )

    class Meta:
        verbose_name = _("Trabajo de búsqueda")
        verbose_name_plural = _("Trabajos de búsqueda")
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"Job #{self.pk} — {self.status} — {self.query[:50]}"


class Notebook(models.Model):
    """
    Cuaderno (Notebook) para organizar y analizar artículos.
    Similar a NotebookLM, permite agrupar artículos con notas y análisis.
    """

    title = models.CharField(
        _("Título del cuaderno"),
        max_length=255,
        default=_("Nuevo cuaderno"),
    )
    description = models.TextField(
        _("Descripción"),
        blank=True,
        default="",
    )
    created_at = models.DateTimeField(_("Creado"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Actualizado"), auto_now=True)
    articles = models.ManyToManyField(
        "Article",
        blank=True,
        related_name="notebooks",
        verbose_name=_("Artículos en el cuaderno"),
    )

    class Meta:
        verbose_name = _("Cuaderno")
        verbose_name_plural = _("Cuadernos")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title
