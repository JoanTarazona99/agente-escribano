"""
Management command: limpia artículos atascados en ai_processing=True.

Ejecutar en cada deploy (start.sh) para resetear artículos cuyo análisis
fue interrumpido por un kill del worker o un redeploy de Render.

Uso:
    python manage.py cleanup_stuck_articles
    python manage.py cleanup_stuck_articles --dry-run
"""
from django.core.management.base import BaseCommand

from apps.articles.models import Article


class Command(BaseCommand):
    help = (
        "Resetea artículos con ai_processing=True (análisis interrumpido "
        "por kill del worker o redeploy). Pensado para ejecutarse al "
        "arrancar el servidor."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Solo muestra cuántos artículos se limpiarían, sin modificar la BD.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        stuck = Article.objects.filter(ai_processing=True)
        count = stuck.count()

        if count == 0:
            self.stdout.write("No hay artículos atascados en ai_processing=True.")
            return

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"[dry-run] {count} artículo(s) con ai_processing=True "
                    f"serían reseteados."
                )
            )
            return

        updated = stuck.update(
            ai_processing=False,
            ai_error="Análisis interrumpido (reinicio del servidor)",
            ai_error_code="timeout",
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"{updated} artículo(s) con ai_processing=True reseteados."
            )
        )
