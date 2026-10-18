import asyncio
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from . import __version__
from .config import Settings, settings as default_settings
from .csv_io import export_csv, import_csv
from .db import make_engine, make_sessionmaker
from .images import IMAGE_TYPES, MAX_IMAGE_BYTES, ImageError, fetch_image, save_first_cover
from .migrate import upgrade_database
from .models import Game, GameFormat, GameStatus, Platform
from .providers import IGDBProvider, ScreenScraperProvider, SteamGridDBProvider, SteamProvider, error_message
from .providers.steam import cover_candidates as steam_cover_candidates
from .schemas import (
    CoverFetchIn, CoverSearchOut, CsvImportOut, GameIn, GameOut, GamePage, GameUpdate, MetadataSearchOut, PlatformIn, PlatformOut,
    ProviderOut, ResetIn, ResetOut, ScrapeIn, ScrapeStatusOut, SteamImportOut,
)
from .scraper import Scraper, cover_options
from .seed import DEFAULT_PLATFORMS, seed_platforms

STATIC_DIR = Path(__file__).parent / "static"
ALLOWED_COVER_TYPES = IMAGE_TYPES
USER_AGENT = f"game-library-manager/{__version__}"
MAX_CSV_BYTES = 20 * 1024 * 1024
SORT_FIELDS = {
    "title": Game.title,
    "created_at": Game.created_at,
    "release_year": Game.release_year,
    "purchase_date": Game.purchase_date,
    "platform": Platform.name,
    "format": Game.format,
    "status": Game.status,
    "completion": Game.completion,
    "store": Game.store,
    "purchase_price": Game.purchase_price,
    "rating": Game.rating,
}
SORT_PATTERN = f"^-?({'|'.join(SORT_FIELDS)})$"


def create_app(settings: Settings = default_settings, http_client: httpx.AsyncClient | None = None) -> FastAPI:
    engine = make_engine(settings.resolved_database_url)
    SessionLocal = make_sessionmaker(engine)
    upgrade_database(engine)
    with SessionLocal() as db:
        seed_platforms(db)
    covers_dir = settings.covers_dir

    http = http_client or httpx.AsyncClient(timeout=20, headers={"User-Agent": USER_AGENT})
    steam = SteamProvider(http, settings.steam_api_key, settings.steam_id)
    providers = {
        p.name: p
        for p in (
            IGDBProvider(http, settings.igdb_client_id, settings.igdb_client_secret),
            SteamGridDBProvider(http, settings.steamgriddb_api_key),
            steam,
            ScreenScraperProvider(
                http, settings.screenscraper_dev_id, settings.screenscraper_dev_password,
                settings.screenscraper_user, settings.screenscraper_password,
            ),
        )
    }

    scraper = Scraper(SessionLocal, http, providers, covers_dir, delay=settings.scrape_delay)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        scraper.cancel()
        await http.aclose()

    version = settings.app_version if settings.app_version and settings.app_version != "dev" else __version__
    app = FastAPI(title="Game Library Manager", version=version, lifespan=lifespan)

    @app.middleware("http")
    async def reject_cross_site_writes(request: Request, call_next):
        # No login, so another website open in the browser could post forms here (e.g. a CSV import)
        if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("sec-fetch-site") == "cross-site":
            return Response("Cross-site request blocked", status_code=403)
        return await call_next(request)

    def get_db():
        with SessionLocal() as db:
            yield db

    def to_out(game: Game) -> GameOut:
        out = GameOut.model_validate(game)
        if game.cover_path:
            out.cover_url = f"/covers/{game.cover_path}"
        return out

    def get_game_or_404(db: Session, game_id: int) -> Game:
        game = db.get(Game, game_id, options=[selectinload(Game.platform)])
        if not game:
            raise HTTPException(404, "Game not found")
        return game

    def check_platform(db: Session, platform_id: int) -> None:
        if not db.get(Platform, platform_id):
            raise HTTPException(422, "Unknown platform_id")

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": version}

    @app.get("/api/about")
    def about(db: Session = Depends(get_db)):
        return {
            "version": version,
            "commit": settings.git_sha or None,
            "ref": settings.git_ref or None,
            "build_date": settings.build_date or None,
            "database": engine.dialect.name,
            "schema": db.scalar(text("SELECT version_num FROM alembic_version")),
        }

    @app.get("/api/platforms", response_model=list[PlatformOut])
    def list_platforms(db: Session = Depends(get_db)):
        return db.scalars(select(Platform).order_by(Platform.manufacturer, Platform.name)).all()

    @app.post("/api/platforms", response_model=PlatformOut, status_code=201)
    def create_platform(data: PlatformIn, db: Session = Depends(get_db)):
        platform = Platform(**data.model_dump())
        db.add(platform)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "Platform already exists")
        return platform

    @app.get("/api/games", response_model=GamePage)
    def list_games(
        q: str | None = None,
        platform_id: int | None = None,
        format: GameFormat | None = None,
        status: list[GameStatus] = Query(default=[]),
        sort: str = Query("title", pattern=SORT_PATTERN),
        limit: int = Query(100, ge=1, le=500),
        offset: int = Query(0, ge=0),
        db: Session = Depends(get_db),
    ):
        stmt = select(Game)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(or_(
                Game.title.ilike(like), Game.barcode == q, Game.notes.ilike(like), Game.tags.ilike(like),
                Game.publisher.ilike(like), Game.developer.ilike(like), Game.series.ilike(like),
            ))
        if platform_id:
            stmt = stmt.where(Game.platform_id == platform_id)
        if format:
            stmt = stmt.where(Game.format == format)
        if status:
            stmt = stmt.where(Game.status.in_(status))
        total = db.scalar(select(func.count()).select_from(stmt.subquery()))
        key = sort.lstrip("-")
        if key == "platform":
            stmt = stmt.join(Platform, Game.platform_id == Platform.id)
        column = SORT_FIELDS[key]
        # Games without a value go last in either direction
        order = (column.desc() if sort.startswith("-") else column.asc()).nulls_last()
        games = db.scalars(
            stmt.options(selectinload(Game.platform)).order_by(order, Game.id).limit(limit).offset(offset)
        ).all()
        return GamePage(total=total, items=[to_out(g) for g in games])

    @app.post("/api/games", response_model=GameOut, status_code=201)
    def create_game(data: GameIn, db: Session = Depends(get_db)):
        check_platform(db, data.platform_id)
        game = Game(**data.model_dump())
        db.add(game)
        db.commit()
        return to_out(get_game_or_404(db, game.id))

    @app.get("/api/games/{game_id}", response_model=GameOut)
    def get_game(game_id: int, db: Session = Depends(get_db)):
        return to_out(get_game_or_404(db, game_id))

    @app.patch("/api/games/{game_id}", response_model=GameOut)
    def update_game(game_id: int, data: GameUpdate, db: Session = Depends(get_db)):
        game = get_game_or_404(db, game_id)
        changes = data.model_dump(exclude_unset=True)
        if "platform_id" in changes:
            check_platform(db, changes["platform_id"])
        for key, value in changes.items():
            setattr(game, key, value)
        db.commit()
        db.expire(game)
        return to_out(get_game_or_404(db, game_id))

    @app.delete("/api/games/{game_id}", status_code=204)
    def delete_game(game_id: int, db: Session = Depends(get_db)):
        game = get_game_or_404(db, game_id)
        if game.cover_path:
            (covers_dir / game.cover_path).unlink(missing_ok=True)
        db.delete(game)
        db.commit()

    @app.put("/api/games/{game_id}/cover", response_model=GameOut)
    def upload_cover(game_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
        game = get_game_or_404(db, game_id)
        ext = ALLOWED_COVER_TYPES.get(file.content_type or "")
        if not ext:
            raise HTTPException(415, "Cover must be JPEG, PNG or WebP")
        content = file.file.read(MAX_IMAGE_BYTES + 1)
        if len(content) > MAX_IMAGE_BYTES:
            raise HTTPException(413, "Cover too large (max 10 MB)")
        filename = f"{game.id}-{uuid.uuid4().hex[:8]}{ext}"
        (covers_dir / filename).write_bytes(content)
        replace_cover(game, filename)
        db.commit()
        return to_out(get_game_or_404(db, game_id))

    def get_provider(name: str):
        provider = providers.get(name)
        if not provider or not provider.enabled:
            raise HTTPException(404, f"Provider '{name}' not available")
        return provider

    def replace_cover(game: Game, filename: str) -> None:
        if game.cover_path:
            (covers_dir / game.cover_path).unlink(missing_ok=True)
        game.cover_path = filename

    @app.get("/api/providers", response_model=list[ProviderOut])
    def list_providers():
        return [
            ProviderOut(name=p.name, label=p.label, enabled=p.enabled, can_import=p is steam and steam.can_import)
            for p in providers.values()
        ]

    async def search_providers(q: str, provider: str | None = None):
        selected = [get_provider(provider)] if provider else [p for p in providers.values() if p.enabled]
        outcomes = await asyncio.gather(*(p.search(q) for p in selected), return_exceptions=True)
        results, errors = [], {}
        for p, outcome in zip(selected, outcomes):
            if isinstance(outcome, Exception):
                errors[p.name] = error_message(outcome)
            else:
                results.extend(outcome)
        return results, errors

    @app.get("/api/metadata/search", response_model=MetadataSearchOut)
    async def metadata_search(q: str = Query(min_length=1), provider: str | None = None):
        results, errors = await search_providers(q, provider)
        return MetadataSearchOut(results=[r.__dict__ for r in results], errors=errors)

    @app.get("/api/covers/search", response_model=CoverSearchOut)
    async def cover_search(q: str = Query(min_length=1), platform: str = ""):
        """All covers the providers have for a title, to pick one by hand (closest title matches first)."""
        results, errors = await search_providers(q)
        return CoverSearchOut(options=cover_options(q, platform, results, providers), errors=errors)

    @app.get("/api/metadata/image")
    async def metadata_image(provider: str, url: str):
        """Image proxy so thumbnails load without exposing provider credentials to the browser."""
        try:
            content, content_type = await fetch_image(http, get_provider(provider), url)
        except (ImageError, httpx.HTTPError) as exc:
            raise HTTPException(502, error_message(exc))
        return Response(content, media_type=content_type, headers={"Cache-Control": "max-age=86400"})

    @app.post("/api/games/{game_id}/cover/fetch", response_model=GameOut)
    async def fetch_cover(game_id: int, data: CoverFetchIn, db: Session = Depends(get_db)):
        game = get_game_or_404(db, game_id)
        try:
            filename = await save_first_cover(http, get_provider(data.provider), data.urls, covers_dir, game.id)
        except ImageError as exc:
            raise HTTPException(502, f"Could not download cover: {exc}")
        replace_cover(game, filename)
        db.commit()
        return to_out(get_game_or_404(db, game_id))

    def scrape_status(db: Session) -> ScrapeStatusOut:
        return ScrapeStatusOut(
            **scraper.status_dict(),
            never_scraped=db.scalar(select(func.count(Game.id)).where(Game.scraped_at.is_(None))),
            library_total=db.scalar(select(func.count(Game.id))),
            providers=[p.label for p in scraper.enabled_providers],
        )

    @app.get("/api/scrape", response_model=ScrapeStatusOut)
    def get_scrape(db: Session = Depends(get_db)):
        return scrape_status(db)

    @app.post("/api/scrape", response_model=ScrapeStatusOut, status_code=202)
    async def start_scrape(data: ScrapeIn, db: Session = Depends(get_db)):
        try:
            scraper.start(data.mode)
        except RuntimeError as exc:
            raise HTTPException(409, str(exc))
        return scrape_status(db)

    @app.post("/api/scrape/cancel", response_model=ScrapeStatusOut)
    def cancel_scrape(db: Session = Depends(get_db)):
        scraper.cancel()
        return scrape_status(db)

    async def download_steam_covers(game_ids: list[int]) -> None:
        for game_id in game_ids:
            with SessionLocal() as db:
                game = db.get(Game, game_id)
                if not game or game.cover_path or not game.steam_appid:
                    continue
                try:
                    filename = await save_first_cover(
                        http, steam, steam_cover_candidates(game.steam_appid), covers_dir, game.id
                    )
                except ImageError:
                    continue
                game.cover_path = filename
                db.commit()

    @app.post("/api/import/steam", response_model=SteamImportOut)
    async def import_steam(background: BackgroundTasks, db: Session = Depends(get_db)):
        if not steam.can_import:
            raise HTTPException(400, "Set STEAM_API_KEY and STEAM_ID to import your Steam library")
        try:
            owned = await steam.owned_games()
        except httpx.HTTPError as exc:
            raise HTTPException(502, f"Steam API error: {error_message(exc)}")
        pc = db.scalar(select(Platform).where(Platform.name == "PC"))
        existing = set(db.scalars(select(Game.steam_appid).where(Game.steam_appid.is_not(None))))
        new_games = [
            Game(
                title=item.get("name") or f"Steam app {item['appid']}",
                platform_id=pc.id,
                format=GameFormat.digital,
                store="Steam",
                steam_appid=item["appid"],
            )
            for item in owned
            if item["appid"] not in existing
        ]
        db.add_all(new_games)
        db.commit()
        background.add_task(download_steam_covers, [g.id for g in new_games])
        return SteamImportOut(imported=len(new_games), skipped=len(owned) - len(new_games))

    @app.get("/api/stats")
    def stats(db: Session = Depends(get_db)):
        def counts(column, *where):
            rows = db.execute(select(column, func.count(Game.id)).where(*where).group_by(column)).all()
            return {(k.value if hasattr(k, "value") else k): n for k, n in rows}

        collection = Game.status.in_([GameStatus.owned, GameStatus.lent])
        by_platform = db.execute(
            select(Platform.name, func.count(Game.id))
            .join(Game).where(collection).group_by(Platform.name).order_by(func.count(Game.id).desc())
        ).all()
        return {
            "total": db.scalar(select(func.count(Game.id))),
            "collection": db.scalar(select(func.count(Game.id)).where(collection)),
            "by_platform": {name: n for name, n in by_platform},
            "by_format": counts(Game.format, collection),
            "by_status": counts(Game.status),
            "by_completion": counts(Game.completion, collection),
            "total_spent": round(db.scalar(select(func.coalesce(func.sum(Game.purchase_price), 0)).where(collection)) or 0, 2),
            "loaned": db.scalar(select(func.count(Game.id)).where(Game.status == GameStatus.lent)),
        }

    @app.post("/api/reset", response_model=ResetOut)
    def reset_library(data: ResetIn, db: Session = Depends(get_db)):
        """Delete every game, its cover and the platforms the user or an import added."""
        if data.confirm != "BORRAR":
            raise HTTPException(400, 'Send {"confirm": "BORRAR"} to delete the whole library')
        if scraper.status.running:
            raise HTTPException(409, "A cover lookup is running; cancel it first")
        games = db.scalars(select(Game)).all()
        for game in games:
            if game.cover_path:
                (covers_dir / game.cover_path).unlink(missing_ok=True)
            db.delete(game)
        db.flush()
        defaults = {name for name, _ in DEFAULT_PLATFORMS}
        extra = db.scalars(select(Platform).where(Platform.name.not_in(defaults))).all()
        for platform in extra:
            db.delete(platform)
        db.commit()
        seed_platforms(db)
        return ResetOut(games_deleted=len(games), platforms_deleted=len(extra))

    @app.get("/api/export/csv")
    def export(db: Session = Depends(get_db)):
        return Response(
            export_csv(db),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="game-library.csv"'},
        )

    @app.post("/api/import/csv", response_model=CsvImportOut)
    def import_file(
        file: UploadFile = File(...),
        default_format: GameFormat = Form(GameFormat.physical),
        skip_duplicates: bool = Form(True),
        delimiter: Literal["auto", "semicolon", "comma", "tab"] = Form("auto"),
        db: Session = Depends(get_db),
    ):
        raw = file.file.read(MAX_CSV_BYTES + 1)
        if len(raw) > MAX_CSV_BYTES:
            raise HTTPException(413, "CSV too large")
        return import_csv(db, raw, default_format, skip_duplicates, delimiter)

    app.mount("/covers", StaticFiles(directory=covers_dir), name="covers")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # Version the asset URLs so browsers fetch the new JS/CSS after an image update
    asset_version = f"{version}-{settings.git_sha[:7]}" if settings.git_sha else version
    index_html = (STATIC_DIR / "index.html").read_text(encoding="utf-8").replace("{{ASSET_VERSION}}", asset_version)

    @app.get("/", include_in_schema=False)
    def index():
        return HTMLResponse(index_html, headers={"Cache-Control": "no-cache"})

    return app

