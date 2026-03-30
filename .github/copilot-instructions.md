# Copilot Instructions — Agente Escribano

## Visión general del proyecto

Agente de búsqueda y análisis de artículos científicos sobre **disociación/recombinación de moléculas de agua en sistemas electromembrana (ЭМС)**. Busca en arXiv (✅ operativo), eLIBRARY (⚠️ bloqueado por CAPTCHA de IP), Scopus y WOS (stubs); traduce, resume y analiza con un LLM local (Ollama).

**Stack:** Python 3.13 · Django 5.x + DRF · React 18 + Vite + TypeScript · SQLite (→ PostgreSQL en prod) · Ollama local (`qwen2.5-coder:7b`) · Docker Compose

---

## Arquitectura: 3 apps Django + 1 app React

```
backend/apps/
  articles/   → modelos Article + SearchJob, serializers, admin
  search/     → conectores por fuente + SearchOrchestrator
  agent/      → OllamaService (traducción, resumen, análisis IA)
frontend/src/
  components/ → SearchPanel, ArticleCard, MathText, LanguageSwitcher, Navbar
  pages/      → Dashboard, Search, ArticleDetail, Settings
  i18n/       → react-i18next (ES/RU/EN), locales en public/locales/
e2e/          → tests Playwright
```

**Flujo de datos principal:**
`POST /api/search/` → `SearchOrchestrator` → conectores → `Article.save()` → `POST /api/articles/{id}/analyze/` → `OllamaService.process_article()` → campos `ai_*` actualizados

---

## Configuración de entorno

- `backend/config/settings/base.py` lee `.env.dev` en la **raíz del proyecto** (no en `backend/`), usando `django-environ`.
- `DJANGO_SETTINGS_MODULE`: `config.settings.local` (dev) · `config.settings.production` (prod).
- Variables obligatorias: `DJANGO_SECRET_KEY`, `DATABASE_URL`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL`.
- `SCOPUS_API_KEY` / `WOS_API_KEY` pueden estar vacías; sus conectores lanzan `NotImplementedError`.
- Copiar `.env.example` → `.env.dev` para trabajar localmente.

---

## Comandos de desarrollo

```bash
# Con Docker (recomendado)
make dev              # levanta backend + frontend + ollama
make migrate && make pull-model
make test-back        # pytest --cov (objetivo ≥ 80%)
make test-front       # Jest sin watch
make test-e2e         # Playwright

# Sin Docker (Windows, Python 3.13, venv en raíz del proyecto)
cd backend
pip install -r requirements/local.txt
DJANGO_SETTINGS_MODULE=config.settings.local python manage.py migrate
DJANGO_SETTINGS_MODULE=config.settings.local python manage.py runserver
# Frontend
cd frontend && npm install && npm run dev
```

> El venv está en la **raíz** del proyecto (`../.venv`), no dentro de `backend/`.
> En pytest, `DJANGO_SETTINGS_MODULE` se fija en `pyproject.toml` — no hace falta exportarlo.

---

## Patrones y convenciones del código

### Modelos Django
- Campos de texto opcionales: `blank=True, default=""` — **nunca** `null=True` en `CharField`/`TextField`.
- Excepción: `doi` usa `unique=True, null=True` para permitir múltiples artículos sin DOI.
- Enums como `TextChoices` en el mismo fichero de modelo (`SourceDatabase`, `ArticleType`).
- Propiedades computadas en el modelo (`has_doi`, `doi_url`) — no recalcular en serializers.

### Serializers DRF
- Tres serializers por recurso: `ListSerializer` · `DetailSerializer` · `UpdateSerializer`.
- Propiedades del modelo se exponen como `serializers.ReadOnlyField()`.

### Vistas DRF
- `ViewSet` con mixins explícitos (nunca `ModelViewSet`): solo acciones necesarias.
- `@extend_schema` en cada acción para OpenAPI automático.
- Lógica de negocio en `apps/agent/services.py`, nunca en vistas.

### Conectores de búsqueda (`apps/search/connectors/`)
- Heredan de `BaseSearchConnector`; implementan `search(query, max_results) → list[ArticleData]`.
- **arXiv**: usa `httpx`; construye URL manualmente con `.replace(' ', '+')` (evita doble-encoding con httpx). Rate-limit de 3 s + reintentos en 429.
- **eLIBRARY**: usa `curl_cffi` con `impersonate="chrome120"` (bypass TLS/JA3). Detecta `page_captcha.asp` en la URL de respuesta y devuelve `[]` sin lanzar excepción. No es posible scraping desde IPs fuera de Rusia o IPs de VPN bloqueadas.
  - `ELIBRARY_PROXY_URL` en `.env.dev`: proxy residencial ruso opcional (`http://user:pass@host:port`). Si no está definido el conector opera sin proxy.
  - `ELIBRARY_COOLDOWN_HOURS` (default 24): el **orquestador** salta la petición HTTP a eLIBRARY si ya hay artículos de esa fuente guardados en las últimas N horas, devolviendo directamente los resultados de la BD. Poner `0` para deshabilitar.
- **Scopus / WOS**: stubs en `connectors/stubs.py` — lanzan `NotImplementedError`; siempre mockear en tests.
- `SearchOrchestrator` deduplica por `doi` antes de guardar.

```python
# Patrón de test para conectores con sesión externa (eLIBRARY)
@patch("apps.search.connectors.elibrary.cf_requests")
def test_captcha_returns_empty(self, mock_cf):
    session = MagicMock()
    session.get.return_value = MagicMock(url="https://www.elibrary.ru/page_captcha.asp?...")
    mock_cf.Session.return_value = session
    assert ElibraryConnector().search("тест") == []
```

### Servicio Ollama (`apps/agent/services.py`)
- `OllamaService.process_article(article)` escribe `ai_summary`, `ai_analysis`, `title_es`, `abstract_es`, `title_en`, `abstract_en`; marca `ai_processed=True`.
- Mock en tests: `patch("apps.agent.services.ollama.Client")`.

### Frontend — renderizado LaTeX
- Los abstractos de arXiv contienen notación LaTeX (`$H_2O$`, `$$\Delta G$$`).
- Usar siempre `<MathText text={...} />` (en `components/MathText/`) para títulos y abstractos — nunca renderizar como texto plano.
- `MathText` usa `react-katex` + `katex/dist/katex.min.css`; hace fallback a texto original si KaTeX falla.

### Frontend — internacionalización
- Traducciones en `frontend/public/locales/{es,ru,en}/translation.json`.
- Nunca hardcodear strings; usar `useTranslation()`.
- Idioma detectado por `i18next-browser-languagedetector`; fallback: `en`.
- El idioma activo determina qué campo mostrar: `title_es`/`title_en`/`title` según `i18n.language.slice(0,2)`.

---

## Tests (estado actual: 44 backend · 14 frontend)

| Capa | Framework | Comando |
|------|-----------|---------|
| Backend | `pytest` + `pytest-django` | `make test-back` |
| Frontend | Jest + RTL + MSW | `make test-front` |
| E2E | Playwright | `make test-e2e` |

- Tests E2E: breakpoints 375 px / 768 px / 1280 px en `e2e/tests/responsive.spec.ts`.
- MSW intercepta `/api/*` en tests de frontend; fixtures en `frontend/src/tests/fixtures.ts`.
- Para nuevos conectores: mockear siempre la capa HTTP externa (`respx` para httpx, `unittest.mock.patch` para curl_cffi/ollama).

---

## Archivos clave de referencia

| Archivo | Propósito |
|---------|-----------|
| [backend/config/settings/base.py](../backend/config/settings/base.py) | Constantes de configuración y lectura de `.env.dev` |
| [backend/apps/articles/models.py](../backend/apps/articles/models.py) | Modelo `Article` + `SearchJob`, enums, propiedades |
| [backend/apps/articles/views.py](../backend/apps/articles/views.py) | Ejemplo canónico de ViewSet con mixins + `@extend_schema` |
| [backend/apps/search/connectors/arxiv.py](../backend/apps/search/connectors/arxiv.py) | Conector operativo de referencia (httpx, rate-limit, parsing XML) |
| [backend/apps/search/connectors/elibrary.py](../backend/apps/search/connectors/elibrary.py) | Patrón de conector con curl_cffi y captcha gracioso |
| [frontend/src/components/MathText/MathText.tsx](../frontend/src/components/MathText/MathText.tsx) | Renderizado LaTeX en abstracts/títulos |
| [docker-compose.yml](../docker-compose.yml) | Servicios: backend, frontend, ollama |
| [Makefile](../Makefile) | Todos los comandos del flujo de trabajo |
