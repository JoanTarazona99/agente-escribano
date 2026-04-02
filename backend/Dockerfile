# Python 3.13 compatible — multi-stage build
# Para desarrollo local: docker build -t agente-escribano:dev .
# Para producción Render: docker build --build-arg ENV=production -t agente-escribano:prod .

FROM python:3.13-slim

ARG ENV=local

# Dependencias del sistema
RUN apt-get update && apt-get install -y \
    gcc \
    libffi-dev \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar dependencias Python según el entorno
COPY requirements/base.txt requirements/base.txt
COPY requirements/${ENV}.txt requirements/${ENV}.txt
RUN pip install --upgrade pip && pip install -r requirements/${ENV}.txt

# Copiar código fuente
COPY . .

EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2 --timeout 60"]
