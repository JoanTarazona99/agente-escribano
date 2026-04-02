#!/usr/bin/env python
"""
Script de validación de deployment para Render.
Verifica que todos los archivos y configuraciones estén correctos.

Uso:
    cd backend
    python validate_deployment.py
"""
import os
import sys
from pathlib import Path

# Colores para terminal
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"

def check(condition, message):
    """Imprime resultado de validación."""
    if condition:
        print(f"{GREEN}✅{RESET} {message}")
        return True
    else:
        print(f"{RED}❌{RESET} {message}")
        return False

def warn(message):
    """Imprime advertencia."""
    print(f"{YELLOW}⚠️ {RESET} {message}")

def info(message):
    """Imprime información."""
    print(f"{BLUE}ℹ️ {RESET} {message}")

def main():
    print("=" * 70)
    print(f"{BLUE}🔍 Validación de Deployment para Render{RESET}")
    print("=" * 70)
    print()
    
    # ─── 1. Verificar estructura de archivos ──────────────────────────
    print(f"{BLUE}1️⃣  Estructura de Archivos{RESET}")
    print("-" * 70)
    
    checks_passed = 0
    checks_total = 0
    
    files_to_check = [
        ("backend/Dockerfile", "Backend Dockerfile"),
        ("backend/requirements/base.txt", "Requirements base"),
        ("backend/requirements/local.txt", "Requirements local"),
        ("backend/requirements/production.txt", "Requirements production"),
        ("backend/config/settings/base.py", "Settings base"),
        ("backend/config/settings/production.py", "Settings production"),
        ("backend/apps/agent/openrouter_service.py", "OpenRouter service"),
        ("docker-compose.yml", "Docker Compose dev"),
        ("docker-compose.prod.yml", "Docker Compose prod"),
        ("MIGRATION_TO_POSTGRES.md", "Migration guide"),
    ]
    
    for file_path, description in files_to_check:
        full_path = Path(__file__).parent.parent / file_path
        checks_total += 1
        if check(full_path.exists(), f"{description}: {file_path}"):
            checks_passed += 1
    
    print()
    
    # ─── 2. Verificar contenidos de archivos críticos ──────────────────
    print(f"{BLUE}2️⃣  Contenidos de Archivos Críticos{RESET}")
    print("-" * 70)
    
    os.chdir(Path(__file__).parent)
    
    # Dockerfile sin Ollama en build arg
    dockerfile_path = Path("Dockerfile")
    if dockerfile_path.exists():
        dockerfile_content = dockerfile_path.read_text(encoding='utf-8')
        checks_total += 1
        if check(
            "ENV=production" in dockerfile_content,
            "Dockerfile: contiene ARG ENV=production"
        ):
            checks_passed += 1
    
    # docker-compose.prod.yml sin ollama
    compose_prod_path = Path("../docker-compose.prod.yml")
    if compose_prod_path.resolve().exists():
        compose_prod_content = compose_prod_path.resolve().read_text(encoding='utf-8')
        checks_total += 2
        
        # No debe tener servicio ollama
        no_ollama = "ollama:" not in compose_prod_content or "# NOTA: Ollama OMITIDO" in compose_prod_content
        if check(no_ollama, "docker-compose.prod.yml: Ollama OMITIDO (producción)"):
            checks_passed += 1
        
        # Debe tener ENV: production
        if check(
            "ENV: production" in compose_prod_content,
            "docker-compose.prod.yml: usa environment production"
        ):
            checks_passed += 1
    
    # requirements/base.txt sin ollama
    base_req_path = Path("requirements/base.txt")
    if base_req_path.exists():
        base_req_content = base_req_path.read_text(encoding='utf-8')
        checks_total += 1
        if check(
            "ollama" not in base_req_content,
            "requirements/base.txt: Ollama OMITIDO (shared across environments)"
        ):
            checks_passed += 1
    
    # requirements/local.txt con ollama
    local_req_path = Path("requirements/local.txt")
    if local_req_path.exists():
        local_req_content = local_req_path.read_text(encoding='utf-8')
        checks_total += 1
        if check(
            "ollama" in local_req_content,
            "requirements/local.txt: Ollama INCLUIDO (desarrollo local)"
        ):
            checks_passed += 1
    
    # requirements/production.txt
    prod_req_path = Path("requirements/production.txt")
    if prod_req_path.exists():
        prod_req_content = prod_req_path.read_text(encoding='utf-8')
        checks_total += 1
        if check(
            "psycopg" in prod_req_content and "ollama" not in prod_req_content,
            "requirements/production.txt: PostgreSQL incluido, Ollama omitido"
        ):
            checks_passed += 1
    
    print()
    
    # ─── 3. Verificar configuración de Django ──────────────────────
    print(f"{BLUE}3️⃣  Configuración de Django{RESET}")
    print("-" * 70)
    
    # Verificar LLM_PROVIDER en settings
    settings_base_path = Path("config/settings/base.py")
    if settings_base_path.exists():
        settings_content = settings_base_path.read_text(encoding='utf-8')
        checks_total += 3
        
        if check(
            "LLM_PROVIDER" in settings_content,
            "base.py: define LLM_PROVIDER"
        ):
            checks_passed += 1
        
        if check(
            "OPENROUTER_API_KEY" in settings_content,
            "base.py: define OPENROUTER_API_KEY"
        ):
            checks_passed += 1
        
        # Buscar referencia a OpenRouter en services.py en vez de base.py
        services_path = Path("apps/agent/services.py")
        if services_path.exists():
            if check(
                "get_llm_service" in services_path.read_text(encoding='utf-8'),
                "services.py: define get_llm_service() factory function"
            ):
                checks_passed += 1
    
    print()
    
    # ─── 4. Verificar archivos de entorno ──────────────────────────
    print(f"{BLUE}4️⃣  Archivos de Entorno{RESET}")
    print("-" * 70)
    
    env_dev_path = Path("../.env.dev")
    if env_dev_path.resolve().exists():
        env_dev_content = env_dev_path.resolve().read_text()
        checks_total += 2
        
        if check(
            "LLM_PROVIDER" in env_dev_content,
            ".env.dev: contiene LLM_PROVIDER"
        ):
            checks_passed += 1
        
        if check(
            "OPENROUTER_API_KEY" in env_dev_content,
            ".env.dev: contiene OPENROUTER_API_KEY"
        ):
            checks_passed += 1
    else:
        warn(".env.dev no encontrado en raíz (opcional, puede estar en backend/)")
    
    print()
    
    # ─── 5. Verificar OpenRouter Service ──────────────────────────
    print(f"{BLUE}5️⃣  OpenRouter Service{RESET}")
    print("-" * 70)
    
    openrouter_path = Path("apps/agent/openrouter_service.py")
    if openrouter_path.exists():
        openrouter_content = openrouter_path.read_text(encoding='utf-8')
        checks_total += 3
        
        if check(
            "class OpenRouterService" in openrouter_content,
            "openrouter_service.py: clase OpenRouterService definida"
        ):
            checks_passed += 1
        
        if check(
            "_call_openrouter" in openrouter_content,
            "openrouter_service.py: método _call_openrouter implementado"
        ):
            checks_passed += 1
        
        if check(
            "authorization" in openrouter_content.lower(),
            "openrouter_service.py: maneja autorización Bearer token"
        ):
            checks_passed += 1
    
    print()
    
    # ─── 6. Verificar vistas de Django ──────────────────────────
    print(f"{BLUE}6️⃣  Vistas de Django (Factory Pattern){RESET}")
    print("-" * 70)
    
    views_path = Path("apps/articles/views.py")
    if views_path.exists():
        views_content = views_path.read_text(encoding='utf-8')
        checks_total += 1
        
        if check(
            "get_llm_service" in views_content,
            "views.py: usa get_llm_service() en vez de OllamaService directo"
        ):
            checks_passed += 1
    
    print()
    
    # ─── 7. Summary ──────────────────────────────────────────────
    print("=" * 70)
    print(f"{BLUE}📊 Resumen de Validación{RESET}")
    print("=" * 70)
    
    percentage = (checks_passed / checks_total * 100) if checks_total > 0 else 0
    
    print(f"Checks pasados: {GREEN}{checks_passed}{RESET} / {checks_total}")
    print(f"Porcentaje: {GREEN}{percentage:.1f}%{RESET}")
    
    print()
    
    if percentage == 100:
        print(f"{GREEN}🎉 ¡Todos los checks pasaron! Listo para Render.{RESET}")
        print()
        print("Próximos pasos:")
        info("1. Crea PostgreSQL en Render.com")
        info("2. Copia DATABASE_URL de Render")
        info("3. Configura variables de entorno en Render (ver MIGRATION_TO_POSTGRES.md)")
        info("4. Deploy el servicio Web en Render")
        print()
        return 0
    
    elif percentage >= 80:
        print(f"{YELLOW}⚠️  Algunos checks fallaron. Revisa arriba.{RESET}")
        return 1
    else:
        print(f"{RED}❌ Varios checks fallaron. NO deployar aún.{RESET}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
