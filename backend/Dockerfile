# Python 3.13 compatible — multi-stage build
FROM python:3.13-slim

# Dependencias del sistema
RUN apt-get update && apt-get install -y \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar dependencias Python primero (capa cacheada)
COPY requirements/local.txt requirements/local.txt
RUN pip install --upgrade pip && pip install -r requirements/local.txt

# Copiar código fuente
COPY . .

EXPOSE 8000
