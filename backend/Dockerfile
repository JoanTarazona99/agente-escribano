# Python 3.13 compatible para producción en Render
# Para desarrollo local: usar docker-compose.yml que incluye Ollama
# Para producción Render: usa requirements/production.txt sin Ollama

FROM python:3.13-slim

# Dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar y instalar SOLO requirements/production.txt (sin Ollama para ahorrar RAM)
COPY backend/requirements/base.txt requirements/base.txt
COPY backend/requirements/production.txt requirements/production.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements/production.txt

# Copiar código fuente
COPY backend/ .

# Exponemos puerto 8000
# Variables de entorno por defecto para producción
ENV DJANGO_SETTINGS_MODULE=config.settings.production
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Collect static files + migraciones + Gunicorn + django-q2 worker
CMD ["sh", "start.sh"]
