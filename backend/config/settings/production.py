"""Configuración para entorno de producción."""
import environ

from .base import *  # noqa: F401, F403

env = environ.Env()

DEBUG = False

ALLOWED_HOSTS = env.list(
    "DJANGO_ALLOWED_HOSTS",
    default=["agente-escribano.onrender.com", ".onrender.com"],
)

# En producción usar PostgreSQL via DATABASE_URL
# DATABASES ya está configurado en base.py leyendo DATABASE_URL

# Seguridad HTTPS
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Archivos estáticos con WhiteNoise
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")  # noqa: F405
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# CORS: permitir todos los orígenes (API pública sin autenticación).
# El frontend usa un proxy de Render (_redirects) pero el navegador
# aún envía preflights con Origin; esto garantiza que siempre se
# devuelva Access-Control-Allow-Origin.
CORS_ALLOW_ALL_ORIGINS = True
