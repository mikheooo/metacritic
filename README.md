# Metacritic AI Platform — YouTube Let's Play Discovery, Transcript & AI Summary (Stage 6)

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
>
> **Stage 4 Scope**: Semantic Embeddings, pgvector & Similar Games:
> - Canonical representation (`build_game_embedding_text`) deterministically constructed from title, developer, sorted platforms, description, and AI review summaries.
> - Cost-control fingerprinting (`compute_embedding_fingerprint`): skips expensive embedding API calls when input text is unchanged.
> - Vector storage & indexing: PostgreSQL 16 + pgvector (`VECTOR(1536)`) with HNSW cosine distance indexing (`ix_game_embeddings_vector`).
> - Recommendation engine (`SimilarGamesService`): native pgvector cosine similarity ranking (`1.0 - (embedding <=> target)`), self-exclusion invariant, atomic recommendation replacement (`similar_games` cache).
> - Frontend UI: interactive Similar Games card grid on `/games/:id` with match percentage indicators.
>
> **Stage 5 Scope**: Hourly Scheduler, Run Now & Realtime Monitoring:
> - Hourly Celery Beat scheduler with UTC crontab (`crontab(minute=0, hour="*")`) running in a dedicated single Beat container (`celery-beat`).
> - Unified application orchestrator (`MetacriticPipelineService`) for both scheduled and manual invocations, preserving daily New Releases vs Browse cursor semantics (`DailyCrawlState` and `DailyGameProcessing` invariants).
> - Concurrency protection: Redis distributed lock (`CrawlLock`) + DB active run check returning HTTP 409 Conflict if active.
> - Schema evolution: Alembic migration `005_crawl_runs_evolution_and_events.py` adding rich `crawl_runs` metadata and append-only `crawl_run_events` audit table indexed by `(crawl_run_id, id)`.
> - Realtime monitoring API: `GET /api/monitor/status`, `GET /api/monitor/runs`, `GET /api/monitor/runs/{id}`, `GET /api/monitor/stream` (SSE with `Last-Event-ID` cursor reconnection).
> - Realtime frontend UI (`/monitor`): scheduler status, Celery worker reachability, Run Now trigger, active run progress bar, counters, live SSE event stream timeline, and durable run history.
> - Dynamic platform filter: `GET /api/platforms` replacing hardcoded platform choices in `GamesPage.tsx`.
>
> **Stage 6 Scope**: YouTube Let's Play Discovery, Transcript & AI Summary:
> - Decoupled YouTube Data API v3 search provider (`YouTubeSearchProvider` Protocol, `YouTubeDataApiProvider`, `FakeYouTubeSearchProvider`).
> - Strict candidate relevance filtering rejecting trailers, OSTs, reviews, reactions, dev diaries, and shorts, ranked by view count descending.
> - Transcript acquisition via `youtube-transcript-api` (`TranscriptProvider` Protocol, `YouTubeTranscriptApiProvider`, `FakeTranscriptProvider`) with fallback if top candidate transcript is unavailable.
> - AI video summarizer with prompt injection defense, structured summary & key points, and bounded transcript chunking.
> - Database schema: Alembic migration `006_youtube_letsplay.py` adding `game_youtube_videos`, `youtube_transcripts`, `youtube_summaries` tables and `crawl_runs.youtube_processed_count`.
> - Pipeline integration: Substage E in hourly crawler pipeline, non-fatal failure isolation, SSE events, and Celery tasks (`tasks.enrich_game_youtube`, `tasks.enrich_missing_youtube`).
> - CLI commands: `python -m app.cli youtube --game-id <id>`, `--missing`, `--all`, `--force`.
> - API & UI: Game Detail API exposing `lets_play` (excluding raw transcript), React card with thumbnail, channel, duration, view count, transcript badge, AI summary, key points, and "Watch on YouTube" button.



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

## Current Status: Stage 5 COMPLETE (Hourly Scheduler, Run Now & Realtime Monitoring)

### Pipeline Orchestration & Monitoring Architecture

- **Unified Application Orchestrator (`MetacriticPipelineService`)**:
  - Handles both automated Celery Beat hourly runs and manual `/api/crawler/run` (Run Now) triggers through a single deterministic service.
  - Maintains Stage 2 daily calendar cycle: first run of each UTC calendar day starts with *Games → New Releases*; subsequent runs advance the persistent *Browse → Newest* cursor.
  - Deduplication invariant: `DailyGameProcessing` with `(processing_date, game_external_id)` unique constraint prevents duplicate processing within the same calendar day.
  - Granular stage transitions: `queued` → `discovering` → `ingesting` → `reviews` → `summaries` → `embedding` → `similarity` → `completed`.
  - Resilience: per-game failure isolation ensures downstream review/summary/embedding failures never rollback the game record.
  - Single similarity rebuild: `rebuild_similar_games` runs once at the end of the batch across all embedded games.

- **Production Batch Contract (Run Now & Scheduler)**:
  - Both automated Celery Beat runs and manual public `Run Now` invocations strictly enforce the canonical production batch size of **20 games** (`settings.CRAWL_BATCH_LIMIT = 20`).
  - Public API `POST /api/crawler/run` requires no request body and ignores client-supplied limit overrides; batch sizing is strictly managed server-side.
  - Small custom limits (`limit < 20`) are restricted to internal developer tooling (CLI: `python -m app.cli crawl --limit <N>`, internal Celery test dispatches, and unit test fixtures).

- **Hourly Scheduling (`celery-beat`)**:
  - Celery Beat scheduler configured with `crontab(minute=0, hour="*")` in UTC.
  - Exactly one Celery Beat instance running in Docker Compose (`celery-beat`) to guarantee no duplicate job dispatch.
  - Dispatches canonical production batch: `limit=20`, `trigger_type="scheduled"`.

- **Concurrency Protection**:
  - Dual protection: Redis distributed lock (`metacritic:crawl_run:lock`) with 1-hour TTL + database active run check (`pending` / `running`).
  - Concurrent manual `Run Now` requests while a run is active return immediate HTTP 409 Conflict with `active_run_id` without polluting the database.


- **Schema Evolution & Audit Log (`Alembic 005`)**:
  - `crawl_runs` table extended with: `task_id`, `target_count`, `discovered_count`, `processed_count`, `failed_count`, `reviews_processed_count`, `summaries_generated_count`, `embeddings_generated_count`, `current_stage`, `current_game_id`, `current_game_title`, `started_at`, `heartbeat_at`, `finished_at`, `error_summary`.
  - Append-only `crawl_run_events` table with compound index `ix_crawl_run_events_run_id` on `(crawl_run_id, id)` capturing sanitized event payloads.

- **Realtime Monitoring API & SSE**:
  - `GET /api/monitor/status`: Scheduler config, worker reachability ping, active run snapshot, and last completed/failed run.
  - `GET /api/monitor/runs`: Durable, paginated history of crawl runs with event lists.
  - `GET /api/monitor/runs/{id}`: Detailed view of a specific run with chronological event timeline.
  - `GET /api/monitor/stream`: Realtime Server-Sent Events (SSE) streaming snapshot, append-only events, and reconnection cursor support via `Last-Event-ID`.
  - `GET /api/platforms`: Dynamic, distinct, normalized platforms from the database.

- **Realtime Frontend UI (`/monitor`)**:
  - Responsive dark-theme dashboard matching the Metacritic AI design language.
  - Status cards: Scheduler state & countdown, Celery Worker reachability (online/offline with worker name), Run Now button with loading state.
  - Active Run Monitor: Stage pill badge, progress bar, counters (Discovered, Games, Reviews, Summaries, Embeddings, Errors), current game title.
  - Live SSE Event Stream Timeline: Scrollable terminal-styled timeline with timestamp, stage badge, event name, and details.
  - Run History: Paginated table of past runs with status badges, trigger types, durations, processed/target counters, and expandable event drawers.
  - Dynamic platform filter on `/games` loaded from `GET /api/platforms`.

### Stage 5 Checklist
- [x] Celery Beat hourly crontab (`crontab(minute=0, hour="*")`) in UTC
- [x] Dedicated single Beat instance in `docker-compose.yml` (`celery-beat`)
- [x] Unified application orchestrator (`MetacriticPipelineService`) for scheduled & manual runs
- [x] Calendar day deduplication preserved via `DailyGameProcessing` and `DailyCrawlState`
- [x] Concurrency protection via Redis lock (`CrawlLock`) returning HTTP 409 Conflict
- [x] Alembic migration `005_crawl_runs_evolution_and_events.py` applied and tested
- [x] Append-only `crawl_run_events` table with compound index on `(crawl_run_id, id)`
- [x] Realtime monitoring REST endpoints (`GET /api/monitor/status`, `runs`, `runs/{id}`)
- [x] Realtime Server-Sent Events (`GET /api/monitor/stream`) with `Last-Event-ID` reconnection cursor
- [x] Dynamic platform endpoint (`GET /api/platforms`) integrated into `GamesPage.tsx`
- [x] Realtime frontend UI (`/monitor`) with status cards, Run Now, active progress, SSE timeline, and run history
- [x] 96 automated tests passing (scheduler, concurrency, pipeline service, monitor API, SSE stream)
- [x] Live end-to-end controlled run verification in Docker Compose (17 events captured, 2 games ingested & embedded, similarity rebuilt, 0 duplicate daily ledger entries)
- [x] Clean Ruff (0 lint errors) and mypy (0 type errors across 57 source files) validation

---

## Current Status: Stage 6 (YouTube Let's Play Discovery, Transcript & AI Summary)

### YouTube Enrichment Architecture

- **Search Provider Abstraction (`YouTubeSearchProvider`)**:
  - `YouTubeDataApiProvider`: queries official Google YouTube Data API v3 (`GET /youtube/v3/search`, `GET /youtube/v3/videos`) via `httpx.AsyncClient` with video category, duration, view count, and snippet enrichment.
  - `FakeYouTubeSearchProvider`: deterministic in-memory provider for unit and integration testing without external network or quota consumption.
  - Query formatting: `"{game.title} gameplay walkthrough let's play"`.

- **Deterministic Candidate Relevance Filter (`evaluate_candidate_relevance`)**:
  - Case-insensitive negative keyword rejection: filters out trailers, OSTs/soundtracks, video reviews ("Before You Buy", "Review"), reaction videos, dev diaries, and shorts (`#shorts` or duration `< 180s`).
  - Strict token overlap verification ensuring candidates belong to the specific game title.
  - Candidate ranking: filtered candidates are sorted by public `view_count DESC`.

- **Transcript Provider (`TranscriptProvider`) & Selection Fallback**:
  - `YouTubeTranscriptApiProvider`: fetches raw speech transcripts via `youtube-transcript-api` (supporting English and Russian language preferences).
  - Popularity-ordered fallback algorithm: iterates candidates in descending view count order. If the top-1 candidate lacks an accessible transcript, the service automatically falls back to rank #2, rank #3, etc. If none have accessible transcripts, the top-1 candidate is retained with status `transcript_unavailable`.

- **AI Video Summarizer (`VideoSummarizer`) & Security**:
  - Prompt injection defense: treats transcripts as untrusted external content with explicit boundary markers and instructions forbidding instruction following within speech text.
  - Length-bounded transcript chunking: samples beginning, middle, and late-game conclusions for long transcripts to fit comfortably in LLM context windows.
  - Output contract: structured summary and key bullet points via `OpenRouterVideoSummarizer`.
  - Cost control: SHA-256 canonical transcript text hashing and compound fingerprinting (`transcript_hash + provider + model + prompt_version + language`) skips expensive LLM calls if the content is unchanged.
  - Search TTL cache: 24-hour refresh window (`YOUTUBE_SEARCH_REFRESH_HOURS=24`) avoids redundant YouTube API search quota usage.

- **Durable Provenance & Database Schema (Alembic 006)**:
  - `game_youtube_videos`: 1:1 relation with `games` table with video ID, URL, title, channel info, duration, view/like counts, selection rank, selection reason, and refresh timestamps.
  - `youtube_transcripts`: 1:1 relation with `game_youtube_videos` with full normalized transcript text, language, is_generated flag, segment count, and SHA-256 text hash.
  - `youtube_summaries`: 1:1 relation with `game_youtube_videos` storing AI summary, JSON key points, model, prompt version, and token usage metrics.
  - `crawl_runs.youtube_processed_count`: integer counter added to `crawl_runs` audit table.

- **Pipeline Integration & Failure Isolation**:
  - Integrated into `MetacriticPipelineService` as downstream Substage E (`stage="youtube"`).
  - YouTube discovery/transcript/summary failures are non-fatal to core game ingestion, review summaries, and embeddings.
  - Emits SSE events `youtube_enrichment_completed` and `youtube_enrichment_failed` during live crawler runs.

- **CLI Tooling & Celery Tasks**:
  - Developer CLI: `python -m app.cli youtube --game-id <id>`, `python -m app.cli youtube --missing`, `python -m app.cli youtube --all`, `python -m app.cli youtube --force`.
  - Background Celery tasks: `tasks.enrich_game_youtube(game_id, force)` and `tasks.enrich_missing_youtube(limit)`.

- **Frontend Card & API**:
  - `GET /api/games/{id}` returns `lets_play` object (excluding large raw transcript payload to optimize response size).
  - Game Detail Page: dedicated **"Popular Let's Play"** card displaying video thumbnail, duration badge, view count, channel name, transcript availability badge, AI summary, key takeaway bullets, and direct "Watch on YouTube" button.
  - Monitor Page: YouTube stage step and "YouTube Enriched" counter box.

### Configuration Variables (`.env`)

```bash
YOUTUBE_API_KEY=               # Google YouTube Data API v3 key (controlled skipping when empty)
YOUTUBE_ENABLED=true           # Master toggle for YouTube enrichment
YOUTUBE_SEARCH_RESULTS_LIMIT=10# Number of search candidates requested per game
YOUTUBE_TRANSCRIPT_LANGUAGES=en,ru # Prioritized transcript language codes
YOUTUBE_SEARCH_REFRESH_HOURS=24# Cache TTL to prevent re-searching recently refreshed games
YOUTUBE_PROMPT_VERSION=v1      # Version string for AI video summary prompts
```

### Stage 6 Verification Checklist
- [x] YouTube Data API v3 search provider with Protocol abstraction (`YouTubeSearchProvider`)
- [x] Candidate relevance filter rejecting trailers, OSTs, reviews, reactions, dev diaries, and shorts
- [x] Transcript acquisition via `youtube-transcript-api` with popularity-ordered fallback
- [x] AI video summarizer with prompt injection defense, structured output, and fingerprint cost control
- [x] Alembic migration `006_youtube_letsplay.py` applied, tested downgrade (-1) and upgrade (head)
- [x] Substage E integrated into `MetacriticPipelineService` with non-fatal failure isolation
- [x] Celery background tasks (`tasks.enrich_game_youtube`, `tasks.enrich_missing_youtube`)
- [x] Developer CLI commands (`python -m app.cli youtube --game-id`, `--missing`, `--all`, `--force`)
- [x] REST API `GET /api/games/{id}` exposes sanitized `lets_play` metadata
- [x] React frontend UI renders "Popular Let's Play" card with AI summary and "Watch on YouTube" link
- [x] 123 automated tests passing in Docker Compose (100% test pass rate)
- [x] Zero Ruff lint errors, zero format issues, zero mypy type issues (66 source files)
- [x] Frontend TypeScript build succeeds with 0 errors
- [x] Secret audit clean (no API keys hardcoded or committed in git)




