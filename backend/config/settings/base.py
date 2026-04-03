"""
Configuración base de Django — compartida entre entornos.
Compatible con Python 3.13 / Django 5.x
"""
from pathlib import Path

import environ

# BASE_DIR apunta a backend/
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Inicializar django-environ
env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
)

# Leer .env en la raíz del proyecto (un nivel arriba de backend/)
# En producción (Docker/Render) el archivo no existe — las vars vienen del entorno
_env_file = BASE_DIR.parent / ".env.dev"
if _env_file.is_file():
    environ.Env.read_env(_env_file)


# ─── Seguridad ────────────────────────────────────────────
SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])


# ─── Aplicaciones ─────────────────────────────────────────
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "corsheaders",
    "drf_spectacular",
]

LOCAL_APPS = [
    "apps.articles",
    "apps.search",
    "apps.agent",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS


# ─── Middleware ───────────────────────────────────────────
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


# ─── Base de datos ────────────────────────────────────────
DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ─── Contraseñas ──────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# ─── Internacionalización ─────────────────────────────────
LANGUAGE_CODE = "es-es"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# ─── Archivos estáticos ───────────────────────────────────
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"


# ─── Django REST Framework ────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "300/min",
        "search": "10/min",
    },
}


# ─── drf-spectacular (OpenAPI) ────────────────────────────
SPECTACULAR_SETTINGS = {
    "TITLE": "Agente Escribano API",
    "DESCRIPTION": (
        "API para búsqueda y análisis de artículos científicos sobre "
        "disociación/recombinación de moléculas de agua en sistemas electromembrana (ЭМС)."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}


# ─── CORS ────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://agente-escribano-site.onrender.com",
    ],
)
CORS_ALLOW_METHODS = [
    "DELETE",
    "GET",
    "OPTIONS",
    "PATCH",
    "POST",
    "PUT",
]
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
]
# Permitir que el navegador cachee la respuesta preflight 1h
CORS_PREFLIGHT_MAX_AGE = 3600


# ─── Ollama / LLM ────────────────────────────────────────
# Proveedor de LLM a usar: 'ollama' (desarrollo local) o 'openrouter' (producción Render)
LLM_PROVIDER = env("LLM_PROVIDER", default="ollama")

# Configuración de Ollama (desarrollo local)
OLLAMA_BASE_URL = env("OLLAMA_BASE_URL", default="http://localhost:11434")
OLLAMA_MODEL = env("OLLAMA_MODEL", default="llama3.2")

# Configuración de OpenRouter (producción Render)
# Obtén tu API key en: https://openrouter.ai/workspaces/default/keys
OPENROUTER_API_KEY = env("OPENROUTER_API_KEY", default="")
# Modelo de OpenRouter:  openrouter/auto | meta-llama/llama-3.1-8b-instruct:free | ...
OPENROUTER_MODEL = env("OPENROUTER_MODEL", default="meta-llama/llama-3.1-8b-instruct:free")


# ─── APIs académicas ─────────────────────────────────────
SCOPUS_API_KEY = env("SCOPUS_API_KEY", default="")
WOS_API_KEY = env("WOS_API_KEY", default="")

# ─── Proxy HTTP (desarrollo local detrás de VPN) ─────────
# Formato: http://127.0.0.1:10809  — vacío = sin proxy.
HTTP_PROXY = env("HTTP_PROXY", default="")

# ─── eLIBRARY ────────────────────────────────────────────
# URL de proxy residencial ruso (opcional). Formato: http://user:pass@host:port
ELIBRARY_PROXY_URL = env("ELIBRARY_PROXY_URL", default="")
# Horas de cooldown entre búsquedas reales en eLIBRARY (minimizar requests).
# Si la última búsqueda exitosa fue hace menos de este tiempo, se omite la
# petición HTTP y se devuelven los artículos ya guardados en BD.
ELIBRARY_COOLDOWN_HOURS = env.int("ELIBRARY_COOLDOWN_HOURS", default=24)
