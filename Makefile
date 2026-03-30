.PHONY: dev dev-build stop test-back test-front test-e2e test-all lint migrate shell pull-model

# ─── Desarrollo ──────────────────────────────────────────
dev:
	docker-compose up

dev-build:
	docker-compose up --build

stop:
	docker-compose down

# ─── Migraciones ─────────────────────────────────────────
migrate:
	docker-compose exec backend python manage.py migrate

makemigrations:
	docker-compose exec backend python manage.py makemigrations

shell:
	docker-compose exec backend python manage.py shell

# ─── Ollama: descargar modelo ────────────────────────────
pull-model:
	docker-compose exec ollama ollama pull llama3.2

# ─── Tests ───────────────────────────────────────────────
test-back:
	docker-compose exec backend pytest --cov=apps --cov-report=term-missing -v

test-front:
	docker-compose exec frontend npm test -- --watchAll=false --coverage

test-e2e:
	cd e2e && npx playwright test

test-all: test-back test-front test-e2e

# ─── Linting ─────────────────────────────────────────────
lint:
	docker-compose exec backend ruff check .
	docker-compose exec frontend npm run lint

# ─── Ejecución local sin Docker ──────────────────────────
local-back:
	cd backend && .venv\Scripts\activate && python manage.py runserver

local-install-back:
	cd backend && python -m venv .venv && .venv\Scripts\pip install -r requirements\local.txt
