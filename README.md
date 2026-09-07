# Metacritic AI Platform — Reviews Ingestion & AI Summaries (Stage 3)

Production-like platform designed to ingest, process, and analyze game data from Metacritic with automated scheduling, AI review insights, embedding similarity, and monitoring.

> **Stage 1 Scope**: Core project skeleton, database schema with constraints, migrations, FastAPI endpoints (`/health`, `/ready`, `/api/games`), Celery infrastructure with diagnostic ping task, React + TypeScript + Vite frontend, Docker Compose orchestration, tests, linting, and architecture documentation.
>
> **Stage 2 Scope**: Production-like Metacritic Ingestion Pipeline:
> - Decoupled HTTP transport (`MetacriticClient`), pure HTML parser (`MetacriticParser`), typed DTOs (`GameCandidate`, `GameDetails`, `PlatformScore`, `BrowsePage`).
> - Daily calendar cycle: first run of each calendar day uses *Games → New Releases*; subsequent runs progress through *Browse → Newest* (`?page=1, 2, ...`).
> - Calendar day deduplication invariant: `DailyGameProcessing` with `(processing_date, game_external_id)` unique constraint.
> - Cursor vs Ledger separation: `DailyCrawlState` is an optimization pointer; `DailyGameProcessing` is the deduplication authority.
> - Redis distributed lock (`CrawlLock`) preventing overlapping scheduled/manual crawler runs.
> - Failure isolation: per-game savepoint rollback; failed games remain eligible for subsequent runs.
> - Developer CLI (`python -m app.cli crawl --limit 20 [--dry-run]`) and Celery task (`tasks.process_metacritic_batch`).
>
> **Stage 3 Scope**: Reviews Ingestion & AI Summaries:
> - Critic reviews and user reviews ingestion: parsed with author, publication, score, platform badge, date, body, and external URL.
> - Strict architectural separation: critic and user reviews are ingested, stored, sampled, and summarized independently.
> - Deterministic sampling (`select_reviews_for_summary`): balances sentiment (positive, mixed, negative) and platform diversity with zero non-determinism.
> - SHA-256 canonical review corpus fingerprinting (`compute_input_fingerprint`): skips expensive LLM calls if the selected review corpus is unchanged.
> - LLM provider abstraction: `ReviewSummarizer` Protocol with production `OpenAIReviewSummarizer` (structured outputs) and `FakeReviewSummarizer`.
> - Prompt injection defenses: treats reviews as untrusted external content with explicit delimiter isolation.
> - Database schema: Alembic migration 002 adding `game_review_summaries` table and review enrichment columns (`platform_id`, `source_url`, `content_hash`).
> - Background Celery tasks (`tasks.enrich_game_reviews`, `tasks.summarize_game_reviews`) and CLI (`python -m app.cli enrich`).
> - Frontend UI on `/games/:id`: visually distinct **"Critics say"** and **"Players say"** consensus cards with 3 likes, 3 dislikes, review counts, and tabbed review explorer.


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

---

## Metacritic Ingestion CLI & Background Tasks

### CLI Usage

The ingestion pipeline can be triggered directly from the CLI for developer inspection and live crawls:

```bash
# Dry-run mode: inspect candidates without database persistence
docker compose run --rm backend python -m app.cli crawl --limit 20 --dry-run

# Live persistence mode: fetch, parse, and persist up to 20 eligible games
docker compose run --rm backend python -m app.cli crawl --limit 20

# Specify custom limit or trigger type
docker compose run --rm backend python -m app.cli crawl --limit 5 --trigger manual

# Enrich a specific game with Metacritic reviews and AI summaries
docker compose run --rm backend python -m app.cli enrich --game-id 11

# Enrich by game slug
docker compose run --rm backend python -m app.cli enrich --slug elden-ring

# Re-summarize existing reviews without re-scraping
docker compose run --rm backend python -m app.cli enrich --game-id 11 --summarize-only

# Generate semantic vector embeddings
docker compose run --rm backend python -m app.cli embed --game-id 11
docker compose run --rm backend python -m app.cli embed --all

# Compute and materialize similar game recommendations
docker compose run --rm backend python -m app.cli similarity --game-id 11
docker compose run --rm backend python -m app.cli similarity --rebuild-all
```

### Celery Task Entrypoints

Scheduled or asynchronous jobs are dispatched via Celery:

```python
from app.workers.tasks import (
    process_metacritic_batch,
    enrich_game_reviews,
    summarize_game_reviews,
    embed_game,
    embed_all_games,
    rebuild_similar_games,
)

# Batch crawl task
crawl_task = process_metacritic_batch.delay(limit=20, trigger_type="scheduled", dry_run=False)

# Review enrichment task (ingest + summarize)
enrich_task = enrich_game_reviews.delay(game_id=11)

# Summarize task (without re-ingesting)
sum_task = summarize_game_reviews.delay(game_id=11, review_type="both")

# Semantic embedding task
embed_task = embed_game.delay(game_id=11)
embed_all_task = embed_all_games.delay()

# Similar games cache rebuild task
sim_task = rebuild_similar_games.delay()
```

---

## Current Status: Stage 4 COMPLETE (Embeddings, pgvector & Similar Games Verified)

### Semantic Embeddings & pgvector Pipeline

- **Canonical Representation (`build_game_embedding_text`)**:
  - Deterministically constructs embedding input from Title, Developer, Platforms (alphabetically sorted), Description, Critic summary, and Player summary.
  - Excludes dynamic metrics (Metascore, Userscore, IDs, timestamps, URLs, tokens) so that scores do not skew semantic similarity. Never outputs literal `"None"`.
- **SHA-256 Fingerprint Cost Control (`compute_embedding_fingerprint`)**:
  - Binds canonical text, provider (`openrouter`), model (`openai/text-embedding-3-small`), dimensions (`1536`), and input version (`v1`).
  - Idempotent: identical fingerprint skips remote embedding API calls (`status="skipped_unchanged"`), incurring zero token cost.
- **pgvector & HNSW Indexing (`game_embeddings`)**:
  - Persisted in PostgreSQL using official `pgvector.sqlalchemy.Vector(1536)` in dedicated `game_embeddings` table.
  - Accelerated via HNSW index: `CREATE INDEX ix_game_embeddings_vector ON game_embeddings USING hnsw (embedding vector_cosine_ops)`.
- **Cosine Similarity Engine (`SimilarGamesService`)**:
  - Executes native PostgreSQL pgvector cosine distance queries:
    ```sql
    SELECT game_id, (1.0 - (embedding <=> :target_vector)) AS similarity_score
    FROM game_embeddings
    WHERE game_id != :source_game_id
    ORDER BY embedding <=> :target_vector ASC
    LIMIT 5;
    ```
  - Invariants: never recommends self, excludes unembedded games, enforces atomic per-game replacement in `similar_games` recommendation cache.
- **Frontend Interaction**:
  - Game Detail view (`/games/:id`) includes interactive **Similar Games** card grid rendering cover images, titles, platform badges, and similarity match percentage indicators.
  - Clicking any card seamlessly navigates to `/games/:similar_game_id` and reloads full game details.

### Checklist
- [x] Full-stack directory structure & container orchestration
- [x] SQLAlchemy 2.0 models with strict constraints (`DailyGameProcessing`, `DailyCrawlState`, `CrawlRun`, `Review`, `GameReviewSummary`, `GameEmbedding`, `SimilarGame`)
- [x] Pure decoupled parser (`MetacriticParser`) with critic/user review extraction and HTML test fixtures
- [x] Resilient HTTP client (`MetacriticClient`) with rate limiting and exponential backoff
- [x] Concurrency protection via Redis distributed lock (`CrawlLock`)
- [x] Calendar day deduplication invariant via `DailyGameProcessing`
- [x] Cursor vs ledger progression (`DailyCrawlState` pointer vs `DailyGameProcessing` truth)
- [x] Deterministic review sampling & LLM structured summaries (OpenRouter + OpenAI compatible)
- [x] Alembic migration 003: pgvector extension, `game_embeddings` table with `VECTOR(1536)`, HNSW cosine index, `similar_games` algorithm version, legacy `games.embedding` dropped
- [x] Embedding provider abstraction (`EmbeddingProvider` protocol, `OpenRouterEmbeddingProvider`, `FakeEmbeddingProvider`)
- [x] Deterministic canonical embedding input builder (`build_game_embedding_text`) and SHA-256 fingerprinting
- [x] Cost-control invariant: identical fingerprint skips embedding API calls (`skipped_unchanged`)
- [x] Vector validation: rejects wrong dimensions, NaN, Infinity, and empty vectors
- [x] PostgreSQL pgvector cosine similarity computation and atomic recommendation cache materialization (`similar_games`)
- [x] Celery background tasks (`tasks.embed_game`, `tasks.embed_all_games`, `tasks.rebuild_similar_games`) and CLI (`python -m app.cli embed`, `python -m app.cli similarity`)
- [x] REST API `GET /api/games/{id}` returns `similar_games` array; raw embeddings never exposed
- [x] Frontend UI on `/games/:id` renders interactive Similar Games card grid with similarity score match badges and seamless routing
- [x] 76 automated tests covering parser, models, API, daily crawler state transitions, sampling, fingerprinting, provider failure, embedding validation, synthetic vector ranking, and similarity constraints
- [x] Controlled live validation: all 11 games embedded via OpenRouter (`openai/text-embedding-3-small`), second unchanged run skips 100%, similarity rebuilt, SQL duplicate/self-reference audits clean
- [x] Clean Ruff (0 lint errors) and mypy (0 type errors across 52 source files) validation


