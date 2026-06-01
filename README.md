# 📝 Agente Escribano

Agente inteligente de escritura y gestión de artículos potenciado por LLMs (OpenRouter). Permite crear, buscar y administrar artículos mediante un agente conversacional con backend Django y frontend TypeScript.

## ✨ Funcionalidades

- 🤖 Agente conversacional con LLMs vía OpenRouter
- 📄 Gestión de artículos (crear, leer, buscar)
- 🔍 Búsqueda semántica de contenido
- 🐘 Persistencia en PostgreSQL
- 🐳 Despliegue completo con Docker + Nginx
- 🧪 Tests e2e incluidos
- ⚙️ CI/CD con GitHub Actions

## 🛠️ Stack Tecnológico

| Capa | Tecnología |
|------|------------|
| Backend | Python · Django · Django REST Framework |
| Frontend | TypeScript · CSS |
| IA / LLM | OpenRouter API |
| Base de datos | PostgreSQL |
| Infraestructura | Docker · Docker Compose · Nginx |
| CI/CD | GitHub Actions |
| Tests | Pytest · E2E |

## 🚀 Inicio Rápido

### Requisitos
- Docker y Docker Compose instalados
- Clave API de OpenRouter

### Instalación

```bash
# Clonar el repositorio
git clone https://github.com/JoanTarazona99/agente-escribano.git
cd agente-escribano

# Configurar variables de entorno
cp .env.example .env
# Editar .env con tu API key de OpenRouter

# Levantar con Docker
docker compose up --build
```

La aplicación estará disponible en `http://localhost`

## 📁 Estructura del Proyecto

```
agente-escribano/
├── backend/          # Django API
│   ├── apps/
│   │   ├── agent/    # Lógica del agente LLM
│   │   ├── articles/ # Gestión de artículos
│   │   └── search/   # Búsqueda
├── frontend/         # Interfaz TypeScript
├── nginx/            # Configuración de proxy
├── e2e/              # Tests end-to-end
└── scripts/          # Scripts de utilidad
```

## 🔧 Variables de Entorno

Copiar `.env.example` a `.env` y configurar:

```env
OPENROUTER_API_KEY=your_api_key_here
DATABASE_URL=postgresql://...
```

## 👤 Autor

**Joan Tarazona** · [GitHub](https://github.com/JoanTarazona99)
