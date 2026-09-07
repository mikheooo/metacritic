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
```

### Celery Task Entrypoints

Scheduled or asynchronous jobs are dispatched via Celery:

```python
from app.workers.tasks import process_metacritic_batch, enrich_game_reviews, summarize_game_reviews

# Batch crawl task
crawl_task = process_metacritic_batch.delay(limit=20, trigger_type="scheduled", dry_run=False)

# Review enrichment task (ingest + summarize)
enrich_task = enrich_game_reviews.delay(game_id=11)

# Summarize task (without re-ingesting)
sum_task = summarize_game_reviews.delay(game_id=11, review_type="both")
```

---

## Current Status: Stage 3.2 COMPLETE (LLM Provenance & Credential Hygiene Verified)

### AI Summarizer Providers & Semantics

The AI summarization layer strictly separates provider identity in DB/API persistence from the underlying client SDK:

- **`OpenRouterReviewSummarizer` (Production Default)**:
  - Connects to OpenRouter gateway (`https://openrouter.ai/api/v1`) using OpenAI-compatible SDK with structured JSON outputs (`beta.chat.completions.parse`).
  - Configured via:
    ```bash
    LLM_PROVIDER=openrouter
    OPENROUTER_API_KEY=sk-or-v1-...
    OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
    LLM_MODEL=openai/gpt-4o-mini
    ```
  - Persists canonical provider as `openrouter` (not `openai`) and model as `openai/gpt-4o-mini`.
  - **Strict Credential Invariant**: If `LLM_PROVIDER=openrouter` and `OPENROUTER_API_KEY` is missing or empty, the factory raises an explicit controlled `ValueError`. **Zero silent fallback to fake.**

- **`OpenAIReviewSummarizer` (Direct OpenAI Mode)**:
  - Connects directly to OpenAI (`https://api.openai.com/v1`).
  - Configured via:
    ```bash
    LLM_PROVIDER=openai
    OPENAI_API_KEY=sk-...
    OPENAI_BASE_URL=https://api.openai.com/v1
    LLM_MODEL=gpt-4o-mini
    ```
  - Persists canonical provider as `openai`.
  - **Strict Credential Invariant**: If `LLM_PROVIDER=openai` and `OPENAI_API_KEY` is missing or empty, raises an explicit controlled `ValueError`. **Zero silent fallback to fake.**

- **`FakeReviewSummarizer` (Testing & Deterministic Local Mode)**:
  - Used strictly for unit tests, regression tests, and explicit local dry-run testing (`LLM_PROVIDER=fake`).
  - Fast, fully deterministic, zero-network summarization.

- **Fingerprinting & Cost Control**:
  - `compute_input_fingerprint` uniquely binds review IDs, content hashes, `provider`, `model`, `prompt_version`, `review_type`, and `language`.
  - The hash is sensitive to provider identity (`openrouter` vs `openai` vs `fake`), ensuring proper regeneration upon configuration change.
  - Subsequent unchanged runs detect the identical fingerprint and strictly bypass LLM calls (`skipped_unchanged`), incurring zero token cost.

### Checklist
- [x] Full-stack directory structure & container orchestration
- [x] SQLAlchemy 2.0 models with strict constraints (`DailyGameProcessing`, `DailyCrawlState`, `CrawlRun`, `Review`, `GameReviewSummary`)
- [x] Pure decoupled parser (`MetacriticParser`) with critic/user review extraction and HTML test fixtures
- [x] Resilient HTTP client (`MetacriticClient`) with rate limiting and exponential backoff
- [x] Concurrency protection via Redis distributed lock (`CrawlLock`)
- [x] Calendar day deduplication invariant via `DailyGameProcessing`
- [x] Cursor vs ledger progression (`DailyCrawlState` pointer vs `DailyGameProcessing` truth)
- [x] Per-game failure isolation with transaction savepoints
- [x] Deterministic review sampling (`select_reviews_for_summary`) with sentiment quota and platform interleaving
- [x] Canonical SHA-256 fingerprinting (`compute_input_fingerprint`) factoring in review corpus, provider, model, and prompt version
- [x] Distinct OpenRouter (`OpenRouterReviewSummarizer`) and direct OpenAI (`OpenAIReviewSummarizer`) implementations with structured outputs
- [x] Strict credential validation for both `openrouter` and `openai` (explicit `ValueError`, no silent fake fallback)
- [x] Input fingerprint sensitivity verified for `provider=openrouter` vs `provider=openai`
- [x] System prompt injection defenses with untrusted `<REVIEWS>` delimiters
- [x] Developer CLI (`python -m app.cli crawl`, `python -m app.cli enrich`) and Celery tasks (`tasks.enrich_game_reviews`, `tasks.summarize_game_reviews`)
- [x] Frontend UI on `/games/:id` rendering "Critics say" and "Players say" cards with 3 likes, 3 dislikes, review counts, provider/model badges, and review tabs
- [x] 61 automated tests covering parser, models, API, daily crawler state transitions, sampling, fingerprinting, provider failure, provider switch, and review enrichment
- [x] Controlled live validation verifying OpenRouter API calls, `provider=openrouter` in DB and REST API, second-run LLM skipping, and Celery task execution
- [x] Clean Ruff and mypy validation (0 errors across 47 source files)


