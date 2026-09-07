from fastapi import APIRouter

from app.api.v1.endpoints import crawler, games, health, monitor, platforms

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(games.router)
api_router.include_router(platforms.router)
api_router.include_router(crawler.router)
api_router.include_router(monitor.router)

