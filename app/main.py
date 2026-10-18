import shutil
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from . import __version__
from .config import Settings, settings as default_settings
from .db import Base, make_engine, make_sessionmaker
from .models import Game, GameFormat, GameStatus, Platform
from .schemas import GameIn, GameOut, GamePage, GameUpdate, PlatformIn, PlatformOut
from .seed import seed_platforms

STATIC_DIR = Path(__file__).parent / "static"
ALLOWED_COVER_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
SORT_FIELDS = {
    "title": Game.title,
    "created_at": Game.created_at,
    "release_year": Game.release_year,
    "purchase_date": Game.purchase_date,
}


def create_app(settings: Settings = default_settings) -> FastAPI:
    engine = make_engine(settings.resolved_database_url)
    SessionLocal = make_sessionmaker(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_platforms(db)
    covers_dir = settings.covers_dir

    app = FastAPI(title="Game Library Manager", version=__version__)

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
        return {"status": "ok", "version": __version__}

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
        status: GameStatus | None = None,
        sort: str = Query("title", pattern="^-?(title|created_at|release_year|purchase_date)$"),
        limit: int = Query(100, ge=1, le=500),
        offset: int = Query(0, ge=0),
        db: Session = Depends(get_db),
    ):
        stmt = select(Game)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(or_(Game.title.ilike(like), Game.barcode == q, Game.notes.ilike(like)))
        if platform_id:
            stmt = stmt.where(Game.platform_id == platform_id)
        if format:
            stmt = stmt.where(Game.format == format)
        if status:
            stmt = stmt.where(Game.status == status)
        total = db.scalar(select(func.count()).select_from(stmt.subquery()))
        column = SORT_FIELDS[sort.lstrip("-")]
        order = column.desc() if sort.startswith("-") else column.asc()
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
        filename = f"{game.id}-{uuid.uuid4().hex[:8]}{ext}"
        with (covers_dir / filename).open("wb") as out:
            shutil.copyfileobj(file.file, out)
        if game.cover_path:
            (covers_dir / game.cover_path).unlink(missing_ok=True)
        game.cover_path = filename
        db.commit()
        return to_out(get_game_or_404(db, game_id))

    @app.get("/api/stats")
    def stats(db: Session = Depends(get_db)):
        by_platform = db.execute(
            select(Platform.name, func.count(Game.id))
            .join(Game).group_by(Platform.name).order_by(func.count(Game.id).desc())
        ).all()
        by_format = db.execute(select(Game.format, func.count(Game.id)).group_by(Game.format)).all()
        return {
            "total": db.scalar(select(func.count(Game.id))),
            "by_platform": {name: n for name, n in by_platform},
            "by_format": {fmt.value: n for fmt, n in by_format},
        }

    app.mount("/covers", StaticFiles(directory=covers_dir), name="covers")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    return app

