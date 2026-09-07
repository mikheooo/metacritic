
from pydantic import BaseModel, ConfigDict


class PlatformBase(BaseModel):
    name: str
    slug: str


class PlatformCreate(PlatformBase):
    pass


class PlatformRead(PlatformBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class GamePlatformRead(BaseModel):
    id: int
    platform_id: int
    platform: PlatformRead
    metascore: int | None = None
    userscore: float | None = None

    model_config = ConfigDict(from_attributes=True)
