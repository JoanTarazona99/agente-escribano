#!/bin/sh
# start.sh - Arranque para produccion (Render free tier, 1 container)
# Lanza Gunicorn + django-q2 qcluster en paralelo.
set -e

echo "==> Collecting static files..."
python manage.py collectstatic --noinput

echo "==> Running migrations..."
python manage.py migrate --noinput

echo "==> Cleaning up stuck articles from previous deploy..."
python manage.py cleanup_stuck_articles --minutes=0

# Refrescar modelos gratuitos de OpenRouter al arrancar.
# Garantiza que llm_models.json este actualizado desde el primer request,
# independientemente del horario del ultimo deploy vs 02:00 UTC.
# El schedule diario de django-q2 hace el refresh posterior cada dia a las 02:00 UTC.
echo "==> Refreshing OpenRouter free models list..."
python manage.py refresh_openrouter_models || echo "WARNING: refresh_openrouter_models fallo (no critico, usando lista anterior)"

echo "==> Starting django-q2 worker (background)..."
python manage.py qcluster &

echo "==> Starting Gunicorn..."
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 2 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
