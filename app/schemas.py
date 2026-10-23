from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    store: str | None = Field(default=None, max_length=100)
    edition: str | None = Field(default=None, max_length=150)
    region: str | None = Field(default=None, max_length=20)
    barcode: str | None = Field(default=None, max_length=50)
    release_year: int | None = Field(default=None, ge=1950, le=2100)
    purchase_date: date | None = None
    purchase_price: float | None = Field(default=None, ge=0)
    notes: str | None = None
    summary: str | None = None
    steam_appid: int | None = None
    loaned_to: str | None = Field(default=None, max_length=150)
    loaned_at: date | None = None
    loan_due: date | None = None
    publisher: str | None = Field(default=None, max_length=150)
    developer: str | None = Field(default=None, max_length=150)
    genre: str | None = Field(default=None, max_length=150)
    series: str | None = Field(default=None, max_length=150)
    search_title: str | None = Field(default=None, max_length=300)
    item_type: str | None = Field(default=None, max_length=50)
    serial_number: str | None = Field(default=None, max_length=100)
    completeness: str | None = Field(default=None, max_length=30)
    condition: str | None = Field(default=None, max_length=50)
    has_box: bool | None = None
    has_manual: bool | None = None
    quantity: int | None = Field(default=None, ge=0)
    current_value: float | None = Field(default=None, ge=0)
    owner: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=150)
    storage_device: str | None = Field(default=None, max_length=150)
    storage_slot: str | None = Field(default=None, max_length=50)
    rating: int | None = Field(default=None, ge=0, le=10)
    tags: str | None = Field(default=None, max_length=500)
    completed_at: date | None = None


class GameIn(GameBase):
    pass


class GameUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    platform_id: int | None = None
    format: GameFormat | None = None
    status: GameStatus | None = None
    completion: CompletionStatus | None = None
    store: str | None = Field(default=None, max_length=100)
    edition: str | None = Field(default=None, max_length=150)
    region: str | None = Field(default=None, max_length=20)
    barcode: str | None = Field(default=None, max_length=50)
    release_year: int | None = Field(default=None, ge=1950, le=2100)
    purchase_date: date | None = None
    purchase_price: float | None = Field(default=None, ge=0)
    notes: str | None = None
    summary: str | None = None
    steam_appid: int | None = None
    loaned_to: str | None = Field(default=None, max_length=150)
    loaned_at: date | None = None
    loan_due: date | None = None
    publisher: str | None = Field(default=None, max_length=150)
    developer: str | None = Field(default=None, max_length=150)
    genre: str | None = Field(default=None, max_length=150)
    series: str | None = Field(default=None, max_length=150)
    search_title: str | None = Field(default=None, max_length=300)
    item_type: str | None = Field(default=None, max_length=50)
    serial_number: str | None = Field(default=None, max_length=100)
    completeness: str | None = Field(default=None, max_length=30)
    condition: str | None = Field(default=None, max_length=50)
    has_box: bool | None = None
    has_manual: bool | None = None
    quantity: int | None = Field(default=None, ge=0)
    current_value: float | None = Field(default=None, ge=0)
    owner: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=150)
    storage_device: str | None = Field(default=None, max_length=150)
    storage_slot: str | None = Field(default=None, max_length=50)
    rating: int | None = Field(default=None, ge=0, le=10)
    tags: str | None = Field(default=None, max_length=500)
    completed_at: date | None = None

    @model_validator(mode="after")
    def _required_not_null(self):
        for name in ("title", "platform_id", "format", "status", "completion"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be empty")
        return self


class BarcodeGameOut(BaseModel):
    id: int
    title: str
    platform: str


class BarcodeOut(BaseModel):
    code: str
    # Games in the library that already have this barcode
    owned: list[BarcodeGameOut] = []
    # Product name from the barcode database, and the title/platform guessed from it
    product: str | None = None
    title: str | None = None
    platform_id: int | None = None
    error: str | None = None


class GameOut(GameBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    platform: PlatformOut
    cover_url: str | None = None
    scraped_at: datetime | None = None
    scrape_error: str | None = None
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


class ProviderTestOut(BaseModel):
    status: Literal["ok", "error", "not_configured"]
    error: str | None = None
    results: int | None = None
    ms: int | None = None
    # Steam only, when the library import is configured: games in the account
    library_games: int | None = None


class MetadataResult(BaseModel):
    provider: str
    external_id: str
    title: str
    release_year: int | None = None
    platforms: list[str] = []
    summary: str | None = None
    publisher: str | None = None
    developer: str | None = None
    genre: str | None = None
    series: str | None = None
    cover_urls: list[str] = []
    thumb_url: str | None = None
    cover_thumbs: list[str] = []


class MetadataSearchOut(BaseModel):
    results: list[MetadataResult]
    errors: dict[str, str]


class CoverOption(BaseModel):
    provider: str
    title: str
    platforms: list[str] = []
    release_year: int | None = None
    urls: list[str]
    thumb_url: str
    matches: bool


class CoverSearchOut(BaseModel):
    options: list[CoverOption]
    errors: dict[str, str]


class CoverFetchIn(BaseModel):
    provider: str
    urls: list[str] = Field(min_length=1, max_length=10)


class SteamImportOut(BaseModel):
    imported: int
    skipped: int


class ImportRowError(BaseModel):
    row: int
    message: str


class CsvImportOut(BaseModel):
    imported: int
    skipped: int
    errors: list[ImportRowError]
    unmapped_columns: list[str]


class ScrapeIn(BaseModel):
    mode: Literal["missing", "all"] = "missing"
    # Provider names to use; empty means every enabled provider
    providers: list[str] = []
    covers: bool = True
    details: bool = True

    @model_validator(mode="after")
    def something_to_do(self):
        if not (self.covers or self.details):
            raise ValueError("Choose covers, details or both")
        return self


class ScrapeStatusOut(BaseModel):
    running: bool
    mode: str | None
    total: int
    done: int
    found: int
    covers: int
    details: int
    not_found: int
    failed: int
    sources: list[str]
    want_covers: bool
    want_details: bool
    current: str | None
    started_at: str | None
    finished_at: str | None
    cancelled: bool
    errors: list[str]
    never_scraped: int
    library_total: int
    providers: list[str]


class ResetIn(BaseModel):
    confirm: str


class ResetOut(BaseModel):
    games_deleted: int
    platforms_deleted: int
