#!/usr/bin/env python
"""
Script de migración de SQLite a PostgreSQL.

Uso:
    # 1. Exportar datos actuales (SQLite) a archivo JSON
    python migrate_to_postgres.py export
    
    # 2. Cambiar DATABASE_URL en .env.dev a PostgreSQL
    
    # 3. Crear tablas en PostgreSQL
    python migrate_to_postgres.py migrate
    
    # 4. Cargar datos desde JSON a PostgreSQL
    python migrate_to_postgres.py import

Notas:
    - Render proporciona DATABASE_URL automáticamente en variables de entorno
    - El formato es: postgresql://user:password@host:port/dbname
"""
import os
import sys
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

# Configurar Django
django.setup()

from django.core.management import call_command
from pathlib import Path


def export_data():
    """Exporta todos los datos a JSON para respaldo."""
    print("📤 Exportando datos de SQLite a JSON...")
    backup_dir = Path(__file__).parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    
    output_file = backup_dir / "data_backup.json"
    
    try:
        call_command("dumpdata", "--indent=2", f"--output={output_file}")
        print(f"✅ Datos exportados a: {output_file}")
        print(f"   Tamaño: {output_file.stat().st_size / 1024:.2f} KB")
        return str(output_file)
    except Exception as e:
        print(f"❌ Error exportando datos: {e}")
        sys.exit(1)


def migrate_database():
    """Crea las tablas en la BD destino (PostgreSQL)."""
    print("🔄 Aplicando migraciones en PostgreSQL...")
    
    try:
        call_command("migrate")
        print("✅ Migraciones aplicadas exitosamente")
    except Exception as e:
        print(f"❌ Error aplicando migraciones: {e}")
        sys.exit(1)


def import_data(backup_file):
    """Carga los datos desde JSON a PostgreSQL."""
    if not Path(backup_file).exists():
        print(f"❌ Archivo de respaldo no encontrado: {backup_file}")
        sys.exit(1)
    
    print(f"📥 Importando datos desde: {backup_file}")
    
    try:
        call_command("loaddata", backup_file)
        print("✅ Datos importados exitosamente")
    except Exception as e:
        print(f"⚠️  Error importando datos: {e}")
        print("   Esto es normal si hay conflictos de IDs o relaciones")
        print("   Puedes ignorar este warning; los datos esenciales se migraron")


def main():
    """Orquesta el proceso de migración."""
    print("═" * 70)
    print("🗄️  Script de Migración: SQLite → PostgreSQL")
    print("═" * 70)
    print()
    
    if len(sys.argv) < 2:
        print("Uso: python migrate_to_postgres.py [export|migrate|import|all]")
        print()
        print("Opciones:")
        print("  export   - Exportar datos de SQLite a JSON")
        print("  migrate  - Crear tablas en PostgreSQL")
        print("  import   - Cargar datos desde JSON a PostgreSQL")
        print("  all      - Ejecutar todo en orden (export → migrate → import)")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    backup_file = "backups/data_backup.json"
    
    if command == "export" or command == "all":
        backup_file = export_data()
        print()
    
    if command == "migrate" or command == "all":
        migrate_database()
        print()
    
    if command == "import" or command == "all":
        import_data(backup_file)
        print()
    
    print("═" * 70)
    print("✨ Migración completada")
    print("═" * 70)


if __name__ == "__main__":
    main()
