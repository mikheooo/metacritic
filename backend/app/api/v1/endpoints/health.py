from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import settings
from app.schemas.health import HealthResponse, ReadyResponse

router = APIRouter(tags=["Health & Readiness"])


@router.get("/health", response_model=HealthResponse, summary="Backend Liveness Check")
async def health_check() -> HealthResponse:
    """
    Lightweight health check indicating that the backend process is running.
    """
    return HealthResponse(status="ok", version="0.1.0")


@router.get(
    "/ready",
    response_model=ReadyResponse,
    responses={
        200: {"description": "Service and database are ready", "model": ReadyResponse},
        503: {"description": "Database is unreachable", "model": ReadyResponse},
    },
    summary="Backend Readiness Check",
)
async def readiness_check(
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """
    Readiness check verifying active connectivity to the PostgreSQL database.
    """
    try:
        await db.execute(text("SELECT 1"))
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "ready", "database": "connected", "error": None},
        )
    except Exception as exc:
        err_detail = str(exc) if settings.DEBUG else "Database connectivity check failed"
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not ready", "database": "disconnected", "error": err_detail},
        )
