"""Admin Django para la app articles."""
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import Article, SearchJob, Notebook


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "title_short",
        "authors_short",
        "year",
        "source_db",
        "article_type",
        "has_doi",
        "ai_processed",
        "created_at",
    ]
    list_filter = ["source_db", "article_type", "ai_processed", "year"]
    search_fields = ["title", "authors", "doi", "keywords"]
    readonly_fields = ["created_at", "updated_at", "doi_url"]
    ordering = ["-year", "-created_at"]

    fieldsets = (
        (_("Identificación"), {"fields": ("title", "authors", "year", "journal", "doi", "doi_url", "url")}),
        (_("Fuente"), {"fields": ("source_db", "source_id")}),
        (_("Contenido original"), {"fields": ("abstract_original", "language_original", "keywords")}),
        (_("Clasificación"), {"fields": ("article_type",)}),
        (_("Traducciones (IA)"), {"fields": ("title_es", "title_en", "abstract_es", "abstract_en")}),
        (_("Análisis IA"), {"fields": ("ai_summary", "ai_analysis", "ai_processed")}),
        (_("Timestamps"), {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(description=_("Título"))
    def title_short(self, obj: Article) -> str:
        return obj.title[:60] + "…" if len(obj.title) > 60 else obj.title

    @admin.display(description=_("Autores"))
    def authors_short(self, obj: Article) -> str:
        return obj.authors[:40] + "…" if len(obj.authors) > 40 else obj.authors

    @admin.display(description=_("Tiene DOI"), boolean=True)
    def has_doi(self, obj: Article) -> bool:
        return obj.has_doi


@admin.register(SearchJob)
class SearchJobAdmin(admin.ModelAdmin):
    list_display = ["id", "query_short", "status", "total_found", "total_saved", "started_at"]
    list_filter = ["status"]
    readonly_fields = ["started_at", "finished_at", "total_found", "total_saved", "error_message"]

    @admin.display(description=_("Consulta"))
    def query_short(self, obj: SearchJob) -> str:
        return obj.query[:60] + "…" if len(obj.query) > 60 else obj.query


@admin.register(Notebook)
class NotebookAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "articles_count", "created_at", "updated_at"]
    list_filter = ["created_at", "updated_at"]
    search_fields = ["title", "description"]
    readonly_fields = ["created_at", "updated_at"]
    filter_horizontal = ["articles"]
    ordering = ["-created_at"]

    fieldsets = (
        (_("Información"), {"fields": ("title", "description")}),
        (_("Artículos"), {"fields": ("articles",)}),
        (_("Timestamps"), {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(description=_("Artículos"))
    def articles_count(self, obj: Notebook) -> int:
        return obj.articles.count()
