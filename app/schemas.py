from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from .models import CompletionStatus, GameFormat, GameStatus


class PlatformIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    manufacturer: str | None = None


class PlatformOut(PlatformIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class GameBase(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    platform_id: int
    format: GameFormat
    status: GameStatus = GameStatus.owned
    completion: CompletionStatus = CompletionStatus.unplayed
    store: str | None = None
    edition: str | None = None
    region: str | None = None
    barcode: str | None = None
    release_year: int | None = Field(default=None, ge=1950, le=2100)
    purchase_date: date | None = None
    purchase_price: float | None = Field(default=None, ge=0)
    notes: str | None = None
    summary: str | None = None
    steam_appid: int | None = None


class GameIn(GameBase):
    pass


class GameUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    platform_id: int | None = None
    format: GameFormat | None = None
    status: GameStatus | None = None
    completion: CompletionStatus | None = None
    store: str | None = None
    edition: str | None = None
    region: str | None = None
    barcode: str | None = None
    release_year: int | None = Field(default=None, ge=1950, le=2100)
    purchase_date: date | None = None
    purchase_price: float | None = Field(default=None, ge=0)
    notes: str | None = None
    summary: str | None = None
    steam_appid: int | None = None


class GameOut(GameBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    platform: PlatformOut
    cover_url: str | None = None
    created_at: datetime
    updated_at: datetime


class GamePage(BaseModel):
    total: int
    items: list[GameOut]


class ProviderOut(BaseModel):
    name: str
    label: str
    enabled: bool
    can_import: bool = False


class MetadataResult(BaseModel):
    provider: str
    external_id: str
    title: str
    release_year: int | None = None
    platforms: list[str] = []
    summary: str | None = None
    cover_urls: list[str] = []
    thumb_url: str | None = None


class MetadataSearchOut(BaseModel):
    results: list[MetadataResult]
    errors: dict[str, str]


class CoverFetchIn(BaseModel):
    provider: str
    urls: list[str] = Field(min_length=1, max_length=10)


class SteamImportOut(BaseModel):
    imported: int
    skipped: int
