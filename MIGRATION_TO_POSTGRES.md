# 🗄️ Guía: Migración SQLite → PostgreSQL en Render

## 📋 Resumen

Este documento explica cómo migrar la base de datos de **SQLite** (desarrollo local) a **PostgreSQL** (producción en Render) para la demo universitaria de Agente Escribano.

---

## 🎯 Requisitos

- ✅ Cuenta en [render.com](https://render.com) (gratis con GitHub)
- ✅ Variables de entorno configuradas en Render (excepto DATABASE_URL)
- ✅ Python 3.13 + venv activado
- ✅ Backend corriendo localmente

---

## 🚀 Paso 1: Crear PostgreSQL en Render

### 1.1 Crear la base de datos

1. Ve a [dashboard.render.com](https://dashboard.render.com)
2. **New +** → **PostgreSQL**
3. Configura:
   - **Name**: `agente-escribano-db`
   - **Database**: `agentodb` (automático)
   - **User**: `agentodb_user` (automático)
   - **Region**: Elige la más cercana (ej: Frankfurt, Ohio)
   - **PostgreSQL Version**: 16
   - **Plan**: Free (⚠️ caducará en 90 días — válido para demo)

4. Click en **Create Database**

### 1.2 Copiar la Database URL

Espera a que le base de datos esté lista (~30 segundos).

En la página de la BD, verás:
```
Internal Database URL:
postgresql://agentodb_user:xxxxx@internal.render.internal:5432/agentodb

External Database URL:
postgresql://agentodb_user:xxxxx@dpg-xxxxx.a.oregon-postgres.render.com:5432/agentodb
```

**Copia la URL externa** (la que termina en `render.com`) — la usarás en Render.

Este es tu `DATABASE_URL`.

---

## 🔄 Paso 2: Migrar Datos Localmente (Opcional pero Recomendado)

### 2.1 Exportar datos actuales (respaldo)

```bash
cd backend
python migrate_to_postgres.py export
```

Verás:
```
📤 Exportando datos de SQLite a JSON...
✅ Datos exportados a: backups/data_backup.json
   Tamaño: 245.32 KB
```

**Checkpoint:** Si algo falla después, tienes el respaldo en `backups/data_backup.json`.

### 2.2 Instalar psycopg2 (driver PostgreSQL)

```bash
pip install psycopg[binary]
```

### 2.3 Cambiar DATABASE_URL en `.env.dev`

Actualiza el archivo `.env.dev`:

```env
# Cambiar esta línea:
DATABASE_URL=sqlite:///db.sqlite3

# A esta:
DATABASE_URL=postgresql://agentodb_user:YOUR_PASSWORD@YOUR_HOST:5432/agentodb
```

**Reemplaza:**
- `YOUR_PASSWORD`: Contraseña da la BD (copia de Render)
- `YOUR_HOST`: Host de Render (ej: `dpg-xxxxx...render.com`)

**Ejemplo completo:**
```env
DATABASE_URL=postgresql://agentodb_user:abc123xyz@dpg-abc123.a.oregon-postgres.render.com:5432/agentodb
```

### 2.4 Crear tablas en PostgreSQL

```bash
# Aplicar migraciones
DJANGO_SETTINGS_MODULE=config.settings.local python manage.py migrate
```

Verás:
```
Operations to perform:
  Apply all migrations: admin, auth, articles, search, agent, ...
  
Running migrations:
  ...
  ✅ OK
```

### 2.5 Cargar datos (opcional)

```bash
python migrate_to_postgres.py import
```

Esto carga todos los 15 artículos y notebooks de tu BD anterior a PostgreSQL.

---

## ✅ Paso 3: Verificar que PostgreSQL Funciona Localmente

```bash
# Reinicia Django
DJANGO_SETTINGS_MODULE=config.settings.local python manage.py runserver
```

Abre el navegador: `http://localhost:8000/api/health/`

Deberías ver:
```json
{
  "database": {"ok": true},
  "llm": {"ok": true, "provider": "openrouter"},
  "stats": {
    "total_articles": 15,
    "ai_processed": 5
  }
}
```

✅ **Si ves `"database": {"ok": true}`, PostgreSQL está funcionando.**

---

## 🌐 Paso 4: Configurar Render (Web Service)

### 4.1 Crear Web Service

1. **New +** → **Web Service**
2. Conecta tu repositorio GitHub
3. Configura:
   - **Name**: `agente-escribano`
   - **Branch**: `main`
   - **Runtime**: Docker
   - **Root Directory**: (dejar vacío)
   - **Build Command**: (dejar como sugiere Render)
   - **Start Command**: (lo configuras abajo)
   - **Plan**: Free

### 4.2 Agregar variables de entorno en Render

En **Environment**, agrega:

```
DJANGO_SECRET_KEY=<generar nuevo>
DJANGO_DEBUG=False
ALLOWED_HOSTS=agente-escribano.onrender.com

DATABASE_URL=postgresql://agentodb_user:PASSWORD@HOST:5432/agentodb

LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-...

CORS_ALLOWED_ORIGINS=https://agente-escribano.onrender.com
VITE_API_URL=https://agente-escribano.onrender.com
```

**Notas:**
- `DJANGO_SECRET_KEY`: Generar con:
  ```python
  python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
  ```
- `DATABASE_URL`: URL de PostgreSQL que copiaste en Paso 1
- `OPENROUTER_API_KEY`: La que ya escopiaste

### 4.3 Start Command

En **Start Command**, reemplaza con:

```bash
python backend/manage.py migrate && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2
```

**Esto garantiza que las migraciones corren ANTES de iniciar Gunicorn.**

### 4.4 Click en **Create Web Service**

Render iniciará el build (toma ~3-5 minutos).

---

## ✅ Paso 5: Verificar Deployment

Una vez que Render muestre **"Live"** (verde):

### 5.1 Health Check

```bash
curl https://agente-escribano.onrender.com/api/health/
```

Deberías ver (igual que localmente):
```json
{
  "database": {"ok": true},
  "llm": {"ok": true, "provider": "openrouter"},
  "stats": {...}
}
```

### 5.2 Buscar artículos

Abre en el navegador:
```
https://agente-escribano.onrender.com
```

Haz una búsqueda. Deberías ver:
- ✅ Conecta a las fuentes (arXiv, eLIBRARY)
- ✅ Guarda artículos en PostgreSQL
- ✅ OpenRouter genera análisis IA

### 5.3 Monitorear Logs

En Render Dashboard → tu app → **Logs**:

Busca:
```
🌐 Usando OpenRouter como provedor LLM
📡 Llamando OpenRouter con modelo: gpt-3.5-turbo
✅ OpenRouter respondió: 2847 caracteres
```

---

## 📊 Resultados Esperados

| Métrica | Valor |
|---------|-------|
| RAM usado | ~200-300 MB (sin Ollama) |
| Cold start | 30-60 segundos (primera vez) |
| Time to first interactivo | ~2 segundos |
| Costo mensual | $0 (Free) |
| Análisis IA | ~$0.005 por artículo |
| BD capacity | 256 MB (Free PostgreSQL) |

---

## 🆘 Troubleshooting

### ❌ "ERROR: psycopg is not installed"

```bash
pip install psycopg[binary]
pip install -r requirements/production.txt
```

### ❌ "Connect to PostgreSQL refused"

- Verifica que copiaste toda la DATABASE_URL (incluido `postgresql://`)
- Verifica la contraseña
- En Render, espera 30s después de crear la BD

### ❌ "table articles_article does not exist"

Render no ejecutó migraciones. En Render panel, reinicia el servicio:
- **Settings** → **Restart Service**

O verifica que el **Start Command** incluye `python manage.py migrate`

### ❌ "OpenRouter API error 401"

Verificación la API Key de OpenRouter:
```bash
curl -H "Authorization: Bearer sk-or-v1-..." \
  https://openrouter.ai/api/v1/chat/completions
```

---

## ✨ ¡Listo para Demo!

Tu aplicación ahora está en:
```
https://agente-escribano.onrender.com
```

¿Preguntas para la demo universitaria?

- **¿Cómo se buscan artículos?** Texto libre + selecciona fuentes (arXiv, eLIBRARY)
- **¿Cómo se genera análisis IA?** Botón azul "Analizar con IA" en el Studio panel
- **¿Qué modelos usa?** OpenRouter (gpt-3.5-turbo) en prod, Ollama (qwen2.5-coder) en dev
- **¿Costo?** $0 (Free Render + crédito inicial OpenRouter)

---

## 🔐 Notas de Seguridad

- ✅ Never commit `.env.dev` con API keys reales
- ✅ Render revuelve credenciales automáticamente cada 90 días (Free tier)
- ✅ HTTPS obligatorio (Render lo proporciona)
- ✅ Database backup automático (Render, 7 días)

---

## 📚 Referencias

- [Render Docs: PostgreSQL](https://render.com/docs/databases)
- [Render Docs: Docker Deploy](https://render.com/docs/docker)
- [Django + PostgreSQL](https://docs.djangoproject.com/en/5.1/ref/databases/#postgresql-notes)
- [OpenRouter API](https://openrouter.ai/docs)
