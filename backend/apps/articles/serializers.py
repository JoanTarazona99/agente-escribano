"""Serializadores DRF para la app articles."""
from rest_framework import serializers

from .models import Article, SearchJob, Notebook

MAX_ABSTRACT_LIST_LENGTH = 200


class TruncatedCharField(serializers.CharField):
    """CharField que trunca el valor a max_length caracteres en la salida."""

    def __init__(self, *args, truncate_to: int = MAX_ABSTRACT_LIST_LENGTH, **kwargs):
        self.truncate_to = truncate_to
        super().__init__(*args, **kwargs)

    def to_representation(self, value):
        text = super().to_representation(value)
        if text and len(text) > self.truncate_to:
            return text[: self.truncate_to] + "…"
        return text


class ArticleListSerializer(serializers.ModelSerializer):
    """Serializador ligero para listados."""

    doi_url = serializers.ReadOnlyField()
    has_doi = serializers.ReadOnlyField()
    abstract_original = TruncatedCharField(read_only=True)
    abstract_es = TruncatedCharField(read_only=True)
    abstract_en = TruncatedCharField(read_only=True)
    abstract_ru = TruncatedCharField(read_only=True)

    class Meta:
        model = Article
        fields = [
            "id",
            "title",
            "title_es",
            "title_en",
            "title_ru",
            "authors",
            "year",
            "journal",
            "doi",
            "doi_url",
            "has_doi",
            "url",
            "source_db",
            "article_type",
            "ai_processed",
            "ai_processing",
            "ai_error",
            "ai_error_code",
            "language_original",
            "created_at",
            "abstract_original",
            "abstract_es",
            "abstract_en",
            "abstract_ru",
        ]
        read_only_fields = ["id", "created_at"]


class ArticleDetailSerializer(serializers.ModelSerializer):
    """Serializador completo para vista de detalle."""

    doi_url = serializers.ReadOnlyField()
    has_doi = serializers.ReadOnlyField()

    class Meta:
        model = Article
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]


class ArticleUpdateSerializer(serializers.ModelSerializer):
    """Serializador para actualizaciones parciales (clasificación manual y renombrado)."""

    class Meta:
        model = Article
        fields = [
            "title",
            "article_type",
            "title_es",
            "title_en",
            "title_ru",
            "abstract_es",
            "abstract_en",
            "abstract_ru",
        ]

    def update(self, instance, validated_data):
        """
        Si el usuario renombra el título base ('title') y los títulos
        en otros idiomas están vacíos o son iguales al anterior, los sincroniza.
        """
        new_title = validated_data.get("title")
        if new_title:
            # Sincronizar idiomas si no tienen valor propio manualmente
            if not validated_data.get("title_es") and (
                not instance.title_es or instance.title_es != new_title
            ):
                validated_data["title_es"] = new_title
            if not validated_data.get("title_en") and (
                not instance.title_en or instance.title_en != new_title
            ):
                validated_data["title_en"] = new_title
            if not validated_data.get("title_ru") and (
                not instance.title_ru or instance.title_ru != new_title
            ):
                validated_data["title_ru"] = new_title

        return super().update(instance, validated_data)


class SearchJobSerializer(serializers.ModelSerializer):
    """Serializador para trabajos de búsqueda."""

    class Meta:
        model = SearchJob
        fields = [
            "id",
            "query",
            "sources",
            "status",
            "total_found",
            "total_saved",
            "error_message",
            "started_at",
            "finished_at",
            "notebook",
        ]
        read_only_fields = [
            "id",
            "status",
            "total_found",
            "total_saved",
            "error_message",
            "started_at",
            "finished_at",
            "notebook",
        ]


class NotebookListSerializer(serializers.ModelSerializer):
    """Serializador ligero para listados de cuadernos."""

    articles_count = serializers.SerializerMethodField()

    class Meta:
        model = Notebook
        fields = [
            "id",
            "title",
            "description",
            "created_at",
            "articles_count",
        ]
        read_only_fields = ["id", "created_at"]

    def get_articles_count(self, obj):
        return obj.articles.count()


class NotebookDetailSerializer(serializers.ModelSerializer):
    """Serializador completo para vista de detalle de cuaderno."""

    articles = ArticleListSerializer(many=True, read_only=True)
    articles_count = serializers.SerializerMethodField()

    class Meta:
        model = Notebook
        fields = [
            "id",
            "title",
            "description",
            "created_at",
            "updated_at",
            "articles",
            "articles_count",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_articles_count(self, obj):
        return obj.articles.count()


class NotebookUpdateSerializer(serializers.ModelSerializer):
    """Serializador para actualizar cuadernos."""

    class Meta:
        model = Notebook
        fields = ["title", "description"]
