"""Configuración para entorno de desarrollo local (SQLite, DEBUG=True)."""
from .base import *  # noqa: F401, F403

DEBUG = True

ALLOWED_HOSTS = ["*"]

# Permitir cualquier origen en desarrollo
CORS_ALLOW_ALL_ORIGINS = True

# Django Debug Toolbar (instalado solo en local.txt)
try:
    import debug_toolbar  # noqa: F401
    INSTALLED_APPS += ["debug_toolbar"]  # noqa: F405
    MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")  # noqa: F405
    INTERNAL_IPS = ["127.0.0.1"]
except ImportError:
    pass

# Emails en consola durante desarrollo
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
