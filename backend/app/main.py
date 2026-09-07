import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.api import api_router
from app.api.v1.endpoints import health
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting Metacritic AI Platform Backend...")
    yield
    logger.info("Shutting down Metacritic AI Platform Backend...")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.1.0",
    description="Production-like foundation for Metacritic ingestion, game analysis, and monitoring.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root-level health and readiness endpoints
app.include_router(health.router)

# Versioned API endpoints (/api/...)
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/", tags=["Root"])
async def root() -> Any:
    return JSONResponse(
        content={
            "name": settings.PROJECT_NAME,
            "version": "0.1.0",
            "docs": "/docs",
            "health": "/health",
            "ready": "/ready",
            "games_api": f"{settings.API_V1_STR}/games",
        }
    )
