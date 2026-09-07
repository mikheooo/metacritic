import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

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
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)


# Unhandled server exception safety handler
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> Response:
    if isinstance(exc, StarletteHTTPException):
        return await http_exception_handler(request, exc)
    if isinstance(exc, RequestValidationError):
        return await request_validation_exception_handler(request, exc)

    logger.exception(
        "Unhandled server exception during %s %s: %s", request.method, request.url.path, exc
    )
    if settings.DEBUG:
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "debug_error": str(exc)},
        )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
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
