# Architecture Overview

This document describes the foundational architecture of the Metacritic Game Analysis platform.

## System Diagram

```
+-------------------------------------------------------------+
|                      React Frontend (Vite)                  |
|   Catalog (/), Detail (/games/:id - Critics/Players Say)   |
+------------------------------+------------------------------+
                               |
                               | HTTP / JSON REST API
                               v
+-------------------------------------------------------------+
|                     FastAPI Backend (v1)                    |
|             /health, /ready, /api/games, /api/games/{id}    |
+------------------------------+------------------------------+
                               |
                               | Async SQLAlchemy 2.0 (asyncpg)
                               v
+-------------------------------------------------------------+
|                   PostgreSQL Database (pgvector)            |
|       Games, Platforms, Reviews, GameReviewSummaries        |
+-------------------------------------------------------------+

                      [ Background Processing & AI ]

+-------------------------------------------------------------+
|                   Review Enrichment Pipeline                |
|  Metacritic Critic/User Ingestion -> Deterministic Sampling |
|      -> Fingerprinting -> LLM Structured Summarization      |
+------------------------------+------------------------------+
                               |
                               | Task Dispatch (Celery / Redis)
                               v
+-------------------------------------------------------------+
|                         Redis 7                             |
|                 Broker + Result Backend                     |
+------------------------------+------------------------------+
                               |
                               | Task Consumer
                               v
+-------------------------------------------------------------+
|                      Celery Workers                         |
|   tasks.process_metacritic_batch, tasks.enrich_game_reviews |
|                 tasks.summarize_game_reviews                |
+-------------------------------------------------------------+
```

---

## Component Responsibilities

### 1. Frontend (React 19 + TypeScript + Vite)
- User interface for browsing ingested games, filtering by platform, searching by title, and sorting by Metascore/UserScore.
- Detail view showing game metadata, platform scores, and visually distinct **"Critics say"** and **"Players say"** cards with synthesized consensus, 3 likes, 3 dislikes, review count badges, and provider information.
- Tabbed individual review explorer for critic and user reviews.
- Monitor dashboard providing visibility into Celery worker status and crawl runs.

### 2. Backend API (FastAPI)
- Exposes structured REST endpoints under `/api`.
- Validates all request parameters with Pydantic v2 schemas.
- Exposes game detail with structured AI summaries and exact database review counts.

- Strictly whitelists sort fields (`metascore`, `userscore`, `title`, `created_at`) and directions (`asc`, `desc`) to prevent SQL injection vulnerabilities.
- Performs health (`/health`) and database connectivity readiness checks (`/ready`).

### 3. Database Layer (PostgreSQL + SQLAlchemy 2.0 + Alembic)
- **Game**: Core catalog entity containing title, external Metacritic identifiers (`metacritic_slug`, `metacritic_url`), media links, developer, summaries, and nullable embedding vector/JSON.
- **Platform & GamePlatform**: Normalized platforms with unique slugs and an explicit M:N association table storing platform-specific Metascore and UserScore, enforced by `UniqueConstraint("game_id", "platform_id")`.
- **Review**: Critic and user reviews with deduplication constraint `UniqueConstraint("game_id", "review_type", "external_id")`.
- **SimilarGame**: Similarity edges with a check constraint `game_id != similar_game_id` and unique pair constraint `UniqueConstraint("game_id", "similar_game_id")`.
- **Crawl Infrastructure**:
  - `CrawlRun`: Audit log of crawl executions (status, trigger_type, timestamps, counts).
  - `DailyCrawlState`: Optimization cursor tracking daily crawl phases (`new_releases`, `browse`) and `browse_page`.
  - `DailyGameProcessing`: **Critical project invariant** guaranteeing no game is processed more than once within the same calendar day via `UniqueConstraint("processing_date", "game_external_id")`.

### 4. Background Infrastructure (Redis + Celery)
- Celery worker connected to Redis for broker and result storage.
- Celery task `tasks.process_metacritic_batch` dispatches batch crawls.
- Concurrency protection via `CrawlLock` leveraging Redis distributed locking with automatic expiration to prevent overlapping runs.

---

## Stage 2 Metacritic Ingestion Pipeline

```
                                  [ Scheduler / CLI / Celery ]
                                                │
                                                ▼
                                   [ Redis Lock (CrawlLock) ]
                                                │
                 ┌──────────────────────────────┴──────────────────────────────┐
                 ▼                                                             ▼
       Phase: "new_releases"                                          Phase: "browse"
  (First run of calendar day)                                  (Subsequent runs of the day)
                 │                                                             │
                 ▼                                                             ▼
     GET /game/ (New Releases)                                  GET /browse/game/.../?page=N
                 │                                                             │
                 └──────────────────────────────┬──────────────────────────────┘
                                                │
                                                ▼
                                    [ MetacriticParser ]
                             (Extract DTOs, Normalization, testids)
                                                │
                                                ▼
                                   [ Daily Ledger Deduplication ]
                           (Skip if external_id in DailyGameProcessing)
                                                │
                                                ▼
                                    [ Ingestion Loop (≤20) ]
                             (Per-Game Atomic Savepoint Isolation)
                                                │
                    ┌───────────────────────────┴───────────────────────────┐
                    ▼                                                       ▼
            [ Game Details HTML ]                                   [ Network/Parse Error ]
            GET /game/{slug}/                                               │
                    │                                                       ▼
                    ▼                                               Rollback savepoint
            Upsert Game entity                                      Error logged
            Upsert Platform & GamePlatform                          Crawl continues!
            Record DailyGameProcessing                              Game remains eligible
            Commit savepoint
```

### Cursor vs. Ledger Semantics

- **`DailyCrawlState` (Optimization Cursor)**:
  - Tracks `phase` (`new_releases` or `browse`) and `browse_page`.
  - Determines *where to search next* to avoid re-fetching pages from the start.
  - Resets automatically at the start of each new calendar day.

- **`DailyGameProcessing` (Deduplication Authority)**:
  - Stores `(processing_date, game_external_id)`.
  - Invariant: A game can be processed at most once per calendar day.
  - Enforced by database `UniqueConstraint("processing_date", "game_external_id")`.
  - Prevents duplicates even if a game appears on multiple browse pages or in both New Releases and Browse.
  - If a game fails during ingestion, its record is rolled back, preserving eligibility for subsequent runs.

### Platform Extraction Scoping & Quality Protection
- **DOM Boundary Scoping**: Platform discovery is strictly scoped to semantic game containers (`data-testid="platform-selector"`, `data-testid="all-platforms"`, and `.game-platforms`). Global document `<a>` links (such as header/footer navigation categories) are excluded.
- **Defensive Navigation & Category Rejection**: Pure function `is_navigation_or_category_label(text)` defensively filters category patterns (`New ... Games`, `Best ... Games`, `Upcoming ... Games`, `Based on ... Reviews`, `Browse ...`), preventing non-platform strings from becoming platforms.
- **Deterministic Normalization**: Pure functions `normalize_platform_slug` and `normalize_platform_name` map aliases (e.g. `ps5` -> `playstation-5`, `switch` -> `nintendo-switch`) to canonical forms (`PlayStation 5`, `Nintendo Switch`, `Xbox Series X`, `PC`).
- **Data Cleanup Migration (004)**: Cleaned legacy contaminated rows, re-pointed alias relationships, and safely preserved genuine platform scores.

---

## Stage 4 Semantic Embedding & Similarity Pipeline

```
[1. Game Entity & Summaries]
      │  Title, developer, description, platform names, critic summary, player summary
      ▼
[2. Canonical Embedding Input Builder]
      │  build_game_embedding_text(): deterministic ordering, whitespace normalization, no "None"
      ▼
[3. Fingerprinting & Cost Control]
      │  compute_embedding_fingerprint(): SHA-256 over canonical text, provider, model, dimensions, v1
      │  Matches existing fingerprint? -> status = "skipped_unchanged", 0 API tokens consumed!
      ▼
[4. Embedding Provider]
      │  OpenRouterEmbeddingProvider: AsyncOpenAI -> openrouter.ai (openai/text-embedding-3-small)
      │  Strict credentials check: missing key -> ValueError (no silent fake fallback)
      ▼
[5. Vector Validation]
      │  validate_vector(): checks len == 1536, validates all elements are finite floats (rejects NaN, Inf)
      ▼
[6. PostgreSQL pgvector Persistence]
      │  game_embeddings table: VECTOR(1536), provider, model, fingerprint
      │  HNSW index: USING hnsw (embedding vector_cosine_ops)
      ▼
[7. Cosine Similarity Engine (PostgreSQL)]
      │  Executes native pgvector cosine distance:
      │  SELECT game_id, (1 - (embedding <=> :target_vector)) FROM game_embeddings
      │  WHERE game_id != :source_game_id ORDER BY embedding <=> :target_vector ASC LIMIT 5
      ▼
[8. Materialized Recommendation Cache]
      │  similar_games table: game_id, similar_game_id, similarity_score, algorithm_version ("cosine-v1")
      │  Atomic replacement per game within a clean transaction (no duplicate pairs, no self-reference)
      ▼
[9. Downstream Delivery]
      │  FastAPI: GET /api/games/{id} exposes similar_games list
      │  React UI: interactive Similar Games card grid with similarity score badge and navigation
```

### Recommendation Cache Scaling Trade-off

- For current catalog scale (hundreds to thousands of games), executing `rebuild_all` recalculates top-K recommendations for all games in sub-second time directly in PostgreSQL leveraging the HNSW vector index.
- For enterprise scale (millions of games), full recomputation would be replaced with an event-driven incremental update where a newly embedded game updates its own top-K and triggers reverse-neighborhood checks on approximate candidate clusters.

---

## Stage 5 Hourly Scheduler, Run Now & Realtime Monitoring

```
+-----------------------------------------------------------------------------------------+
|                                Celery Beat Scheduler                                    |
|   Single container instance (celery-beat) running hourly crontab(minute=0, hour="*")   |
+--------------------------------------------+--------------------------------------------+
                                             |
                                             | Dispatches hourly task
                                             v
+-----------------------------------------------------------------------------------------+
|                                    Celery Worker                                        |
|                          tasks.process_metacritic_pipeline                              |
+--------------------------------------------+--------------------------------------------+
                                             ^
                                             | Dispatches manual task (Run Now)
+--------------------------------------------+--------------------------------------------+
|                            FastAPI Manual Trigger (/crawler/run)                        |
|   Checks DB pending/running + Redis distributed lock (CrawlLock) -> 409 Conflict        |
+--------------------------------------------+--------------------------------------------+
                                             |
                                             v
+-----------------------------------------------------------------------------------------+
|                           MetacriticPipelineService (Unified)                           |
|  - Manages stage transitions: queued -> discovering -> ingesting -> reviews ->          |
|    summaries -> embedding -> similarity -> completed                                    |
|  - Enforces Stage 2 daily calendar cycle: New Releases on first run; Browse afterward   |
|  - Deduplicates via DailyGameProcessing (processing_date, game_external_id)             |
|  - Per-game failure isolation: downstream AI failure never rolls back game entity       |
|  - Rebuilds similarity cache once at the end of the batch                               |
+--------------------------------------------+--------------------------------------------+
                                             |
                                             | Publishes append-only audit events
                                             v
+-----------------------------------------------------------------------------------------+
|                           PostgreSQL Audit & State Tables                               |
|   crawl_runs (metadata, stage, progress counters, heartbeat, error summary)             |
|   crawl_run_events (id, crawl_run_id, stage, event_type, message, payload, created_at)  |
+--------------------------------------------+--------------------------------------------+
                                             ^
                                             | Polled / Streamed via SSE
+--------------------------------------------+--------------------------------------------+
|                             Realtime Monitoring API & SSE                               |
|   GET /api/monitor/status      -> Snapshot of scheduler, worker ping, active run        |
|   GET /api/monitor/runs        -> Durable run history                                   |
|   GET /api/monitor/runs/{id}   -> Detailed run view with chronological event log        |
|   GET /api/monitor/stream      -> SSE stream with Last-Event-ID reconnection cursor     |
|   GET /api/platforms           -> Dynamic clean platforms list from DB                  |
+--------------------------------------------+--------------------------------------------+
                                             ^
                                             | EventSource / REST fetch
+--------------------------------------------+--------------------------------------------+
|                             React Frontend Dashboard (/monitor)                         |
|   - Realtime system status cards (Scheduler, Worker Ping, Run Now action)               |
|   - Active run monitor with progress bar, stage indicator, and real-time counters       |
|   - Live SSE event timeline terminal                                                    |
|   - Historical crawl run log table with expandable event details                        |
+-----------------------------------------------------------------------------------------+
```

### Key Architectural Invariants of Stage 5

1. **Single Scheduler Instance**: Docker Compose defines exactly one `celery-beat` service to prevent duplicate task dispatches.
2. **Deterministic Equivalence**: Scheduled hourly runs and manual `Run Now` invocations invoke the exact same orchestrator (`MetacriticPipelineService`), ensuring consistent cursor advancement, daily deduplication, and database logging.
3. **Dual Concurrency Guard**:
   - Application-level check for active (`pending` or `running`) runs in PostgreSQL.
   - Distributed lock in Redis (`metacritic:crawl_run:lock`) with 3600-second TTL.
   - Concurrent requests receive an immediate `HTTP 409 Conflict` containing the active `run_id`.
4. **Resilient Streaming with Durable Cursors**:
   - `/api/monitor/stream` transmits an initial snapshot followed by new append-only events.
   - Disconnected clients automatically reconnect using the standard `Last-Event-ID` header or query parameter to resume receiving events without loss or duplication.
5. **Dynamic Platform Discovery**:
   - Platforms on `/games` are dynamically fetched from `GET /api/platforms` based on normalized platforms populated by the ingestion pipeline.
6. **Production Batch Contract**:
   - Both Celery Beat and public `Run Now` invocations strictly execute the canonical production batch of 20 games (`settings.CRAWL_BATCH_LIMIT = 20`).
   - The public HTTP API does not allow user-supplied batch limit overrides. Custom small limits (`limit < 20`) are strictly reserved for developer CLI tooling (`app.cli`) and automated test fixtures.

