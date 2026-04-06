"""Management command para refrescar la lista de modelos gratuitos de OpenRouter."""
from django.core.management.base import BaseCommand

from apps.agent.tasks import refresh_openrouter_free_models


class Command(BaseCommand):
    """
    Ejecuta la tarea de refreshar modelos gratuitos de OpenRouter.
    
    Puede ser invocado manualmente:
        python manage.py refresh_openrouter_models
    
    O ser programado en django-q2 para ejecutarse diariamente.
    """
    
    help = "Verifica y actualiza la lista de modelos gratuitos de OpenRouter"

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS("▶ Iniciando refresh de modelos de OpenRouter...")
        )
        try:
            refresh_openrouter_free_models()
            self.stdout.write(
                self.style.SUCCESS("✅ Tarea completada exitosamente")
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Error durante la tarea: {e}")
            )
            raise
