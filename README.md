# Metacritic AI Platform — Foundation (Stage 1)

Production-like foundation for an AI Engineer test project designed to ingest, process, and analyze game data from Metacritic with automated scheduling, review insights, embedding similarity, and monitoring.

> **Stage 1 Scope**: Core project skeleton, database schema with constraints, migrations, FastAPI endpoints (`/health`, `/ready`, `/api/games`), Celery infrastructure with diagnostic ping task, React + TypeScript + Vite frontend, Docker Compose orchestration, tests, linting, and architecture documentation. Scraping, LLMs, and YouTube analysis are deferred to subsequent stages.

---

## Tech Stack

- **Backend**: Python 3.12+, FastAPI, SQLAlchemy 2.0 (asyncio + asyncpg), Alembic, Pydantic v2
- **Database**: PostgreSQL 16 (`pgvector/pgvector:pg16` for vector support in subsequent stages)
- **Background Infrastructure**: Redis 7, Celery 5.4+
- **Frontend**: React 18 / 19, TypeScript, Vite, Nginx
- **Orchestration**: Docker, Docker Compose
- **Quality & Testing**: pytest, pytest-asyncio, Ruff, mypy

---

## Repository Structure

```text
metacritic/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── deps.py
│   │   │   └── v1/
│   │   │       ├── api.py
│   │   │       └── endpoints/
│   │   │           ├── games.py
│   │   │           └── health.py
│   │   ├── core/
│   │   │   └── config.py
│   │   ├── db/
│   │   │   ├── base.py
│   │   │   └── session.py
│   │   ├── models/
│   │   │   ├── base.py
│   │   │   ├── game.py
│   │   │   ├── platform.py
│   │   │   ├── review.py
│   │   │   ├── similar.py
│   │   │   └── crawl.py
│   │   ├── schemas/
│   │   │   ├── common.py
│   │   │   ├── game.py
│   │   │   ├── platform.py
│   │   │   ├── review.py
│   │   │   └── health.py
│   │   ├── services/
│   │   │   └── game_service.py
│   │   ├── workers/
│   │   │   ├── celery_app.py
│   │   │   └── tasks.py
│   │   └── main.py
│   ├── migrations/
│   │   ├── versions/
│   │   │   └── 001_initial_schema.py
│   │   ├── env.py
│   │   └── script.py.mako
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_models.py
│   │   ├── test_api.py
│   │   ├── test_daily_processing.py
│   │   └── test_celery.py
│   ├── alembic.ini
│   ├── Dockerfile
│   └── pyproject.toml
│
├── frontend/
│   ├── src/
│   │   ├── api/client.ts
│   │   ├── components/
│   │   ├── pages/
│   │   │   ├── GamesPage.tsx
│   │   │   ├── GameDetailPage.tsx
│   │   │   └── MonitorPage.tsx
│   │   ├── types/index.ts
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   └── index.css
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── Dockerfile
│   └── nginx.conf
│
├── docs/
│   └── architecture.md
│
├── ai/
│   └── README.md
│
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

---

## Quickstart with Docker Compose

To build and start all containers (`postgres`, `redis`, `backend`, `celery-worker`, `frontend`):

```bash
docker compose up --build -d
```

### Access URLs

- **Frontend Application**: [http://localhost:3000](http://localhost:3000)
- **Backend API & Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Liveness Check**: [http://localhost:8000/health](http://localhost:8000/health)
- **Readiness Check (Database)**: [http://localhost:8000/ready](http://localhost:8000/ready)
- **Games API**: [http://localhost:8000/api/games](http://localhost:8000/api/games)

To verify the Celery diagnostic task in Docker:

```bash
docker compose exec celery-worker python -c "from app.workers.tasks import ping; print('Celery Ping Result:', ping())"
```

To stop containers:

```bash
docker compose down
```

---

## Local Development Setup

### 1. Prerequisites

- Python 3.12+
- Node.js 18+ and npm
- Docker (for PostgreSQL and Redis)

### 2. Environment Configuration

Copy example environment variables:

```bash
cp .env.example .env
```

### 3. Backend Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Run database migrations:

```bash
alembic upgrade head
```

Run the backend server:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Start the Celery worker:

```bash
celery -A app.workers.celery_app worker -l info
```

### 4. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The frontend will run on [http://localhost:3000](http://localhost:3000).

---

## Database Migrations

Apply migrations to head:

```bash
alembic upgrade head
```

Rollback last migration:

```bash
alembic downgrade -1
```

Create a new migration after schema changes:

```bash
alembic revision --autogenerate -m "description_of_changes"
```

---

## Database Invariants & Constraints

- **Game Metacritic URL**: `UniqueConstraint("metacritic_url")`
- **Platform Slug**: `UniqueConstraint("slug")`
- **Game Platform**: `UniqueConstraint("game_id", "platform_id")`
- **Review Deduplication**: `UniqueConstraint("game_id", "review_type", "external_id")`
- **Similar Game Self-Reference**: `CheckConstraint("game_id != similar_game_id")` & `UniqueConstraint("game_id", "similar_game_id")`
- **Daily Game Invariant**: `UniqueConstraint("processing_date", "game_external_id")` ensuring no game is processed more than once per calendar day.

---

## Running Quality Checks and Tests

### Tests (pytest)

```bash
cd backend
pytest -v
```

### Linter (Ruff)

```bash
cd backend
ruff check .
```

### Type Checker (mypy)

```bash
cd backend
mypy app
```

---

## Current Status: Stage 1 COMPLETE

- [x] Full-stack directory structure
- [x] SQLAlchemy 2.0 models with strict constraints
- [x] Initial Alembic migration `001_initial_schema`
- [x] FastAPI `/health`, `/ready`, `/api/games`, `/api/games/{id}`
- [x] Celery diagnostic `ping` task
- [x] React 18 / TypeScript / Vite frontend (`/`, `/games/:id`, `/monitor`)
- [x] Docker Compose multi-service orchestration
- [x] Automated tests covering DB constraints, API, and daily processing invariant
- [x] Ruff and mypy configuration and validation
- [x] Architecture and AI transcript documentation
