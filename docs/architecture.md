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
