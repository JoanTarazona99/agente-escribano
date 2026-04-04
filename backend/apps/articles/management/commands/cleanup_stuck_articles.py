"""
Management command: limpia artículos atascados en ai_processing=True.

Ejecutar en cada deploy (start.sh) para resetear artículos cuyo análisis
fue interrumpido por un kill del worker o un redeploy de Render.

Uso:
    python manage.py cleanup_stuck_articles
    python manage.py cleanup_stuck_articles --dry-run
    python manage.py cleanup_stuck_articles --minutes 5
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.articles.models import Article

# Minutos por defecto: artículos con ai_processing=True y updated_at
# más antiguos que este umbral se consideran atascados.
_DEFAULT_STALE_MINUTES = 10


class Command(BaseCommand):
    help = (
        "Resetea artículos con ai_processing=True cuyo updated_at supere "
        "el umbral de tiempo (default 10 min). Pensado para ejecutarse "
        "al arrancar el servidor o como tarea de mantenimiento."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Solo muestra cuántos artículos se limpiarían, sin modificar la BD.",
        )
        parser.add_argument(
            "--minutes",
            type=int,
            default=_DEFAULT_STALE_MINUTES,
            help=(
                f"Umbral en minutos: solo resetea artículos cuyo updated_at "
                f"sea anterior a ahora - N minutos (default: {_DEFAULT_STALE_MINUTES}). "
                f"Usar 0 para resetear todos sin importar antigüedad."
            ),
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        minutes = options["minutes"]

        stuck = Article.objects.filter(ai_processing=True)
        if minutes > 0:
            cutoff = timezone.now() - timedelta(minutes=minutes)
            stuck = stuck.filter(updated_at__lt=cutoff)

        count = stuck.count()

        if count == 0:
            self.stdout.write("No hay artículos atascados en ai_processing=True.")
            return

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"[dry-run] {count} artículo(s) con ai_processing=True "
                    f"(>{minutes} min) serían reseteados."
                )
            )
            return

        updated = stuck.update(
            ai_processing=False,
            ai_error="Análisis interrumpido (reinicio del servidor)",
            ai_error_code="interrupted",
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"{updated} artículo(s) con ai_processing=True reseteados."
            )
        )
