from datetime import datetime

from pydantic import BaseModel, ConfigDict


class GameBase(BaseModel):
    console: str
    title: str
    path: str
    launch_file: str
    favorite: bool = False
    cover: str | None = None


class GameRead(GameBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    last_played: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ScanResult(BaseModel):
    scanned: int
    added: int
    updated: int
    games: list[GameRead]


class PlayRequest(BaseModel):
    game_id: int


class StatusResponse(BaseModel):
    running: bool
    game: GameRead | None = None
    detail: str | None = None
