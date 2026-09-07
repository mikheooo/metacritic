
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    version: str = "0.1.0"


class ReadyResponse(BaseModel):
    status: str
    database: str
    error: str | None = None
