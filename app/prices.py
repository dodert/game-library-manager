"""Market prices from PriceCharting (www.pricecharting.com/api-documentation).

The API needs a paid subscription token, allows one call a second and returns prices in US
cents. Each item is matched once (by its PriceCharting id, else its barcode, else its title and
platform) and the product found is kept on the item, so later checks follow the same product.
Every check is stored, which is the price history.
"""
import asyncio
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload, sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from .models import Game, GameFormat, GameStatus, PriceCheck
from .providers import error_message

API_URL = "https://www.pricecharting.com/api"
MIN_INTERVAL = 1.1  # seconds between calls; the API blocks more than one a second
# Check columns -> PriceCharting keys
PRICE_KEYS = {
    "loose": "loose-price", "cib": "cib-price", "new": "new-price",
    "box_only": "box-only-price", "manual_only": "manual-only-price", "graded": "graded-price",
}
# Words people (and CLZ) use for completeness -> price column
CONDITION_WORDS = {
    "new": ["new", "nuevo", "sealed", "precintado", "nib", "mint"],
    "cib": ["cib", "complete", "completo", "complete in box"],
    "box_only": ["box only", "solo caja", "caja"],
    "manual_only": ["manual only", "solo manual"],
    "graded": ["graded", "gradeado"],
    "loose": ["loose", "suelto", "cart only", "disc only", "solo cartucho", "solo disco"],
}
# Items whose price is looked up: physical, and not sold
PRICED = (Game.format == GameFormat.physical, Game.status != GameStatus.sold)
COLLECTION = Game.status.in_([GameStatus.owned, GameStatus.lent])


class PriceChartingError(Exception):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def price_condition(game: Game) -> str:
    """Which price fits the item: from its completeness, else box + manual = CIB, else loose."""
    text = re.sub(r"\s+", " ", (game.completeness or "").strip().lower())
    for key, words in CONDITION_WORDS.items():
        if text in words:
            return key
    if game.has_box and game.has_manual:
        return "cib"
    return "loose"


def item_value(game: Game, check: PriceCheck | None) -> int | None:
    """Market value in cents of the item (its condition's price times its quantity)."""
    if not check:
        return None
    price = getattr(check, price_condition(game))
    return None if price is None else price * (game.quantity or 1)


def cents(value: int | None) -> float | None:
    return None if value is None else value / 100


def latest_checks(db: Session, game_ids: list[int] | None = None) -> dict[int, PriceCheck]:
    """Last price check of each item (of the given ones, or all)."""
    last = select(func.max(PriceCheck.id)).group_by(PriceCheck.game_id)
    if game_ids is not None:
        if not game_ids:
            return {}
        last = last.where(PriceCheck.game_id.in_(game_ids))
    return {c.game_id: c for c in db.scalars(select(PriceCheck).where(PriceCheck.id.in_(last)))}


class PriceCharting:
    def __init__(self, http: httpx.AsyncClient, token: str, min_interval: float = MIN_INTERVAL):
        self.http = http
        self.token = token
        self.min_interval = min_interval
        self._lock = asyncio.Lock()
        self._last_call = 0.0

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    async def _get(self, path: str, **params) -> dict:
        # One call at a time, spaced out, whoever asks (bulk job or the item dialog)
        async with self._lock:
            wait = self._last_call + self.min_interval - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                res = await self.http.get(f"{API_URL}/{path}", params={"t": self.token, **params})
            finally:
                self._last_call = time.monotonic()
        try:
            data = res.json()
        except ValueError:
            res.raise_for_status()
            raise PriceChartingError("Invalid response")
        if data.get("status") != "success":
            raise PriceChartingError(data.get("error-message") or f"HTTP {res.status_code}")
        return data

    async def product(self, *, id: int | None = None, upc: str | None = None, q: str | None = None) -> dict:
        params = {"id": id} if id else {"upc": upc} if upc else {"q": q}
        return await self._get("product", **params)

    async def search(self, q: str) -> list[dict]:
        """Up to 20 products: {"id", "name", "console"}."""
        data = await self._get("products", q=q)
        return [
            {"id": int(p["id"]), "name": p.get("product-name"), "console": p.get("console-name")}
            for p in data.get("products") or []
        ]


def new_check(game: Game, product: dict) -> PriceCheck:
    prices = {key: product.get(api_key) for key, api_key in PRICE_KEYS.items()}
    return PriceCheck(
        game_id=game.id, checked_at=utcnow(), product_id=int(product["id"]),
        product_name=(product.get("product-name") or "")[:300] or None,
        console_name=(product.get("console-name") or "")[:150] or None,
        **{k: v if isinstance(v, int) and v > 0 else None for k, v in prices.items()},
    )


async def find_product(client: PriceCharting, game: Game) -> dict:
    """The item's product: its saved id, else its barcode, else "<search title> <platform>"."""
    if game.pricecharting_id:
        return await client.product(id=game.pricecharting_id)
    code = re.sub(r"\D", "", game.barcode or "")
    if 8 <= len(code) <= 14:
        try:
            return await client.product(upc=code)
        except PriceChartingError:
            pass  # not in PriceCharting by barcode; try the title
    query = f"{game.search_title or game.title} {game.platform.name}".strip()
    return await client.product(q=query)


async def check_game(client: PriceCharting, db: Session, game: Game) -> PriceCheck | None:
    """Look the item up now and store the prices. None (and price_error set) when not found."""
    try:
        product = await find_product(client, game)
    except (PriceChartingError, httpx.HTTPError, ValueError) as exc:
        game.price_error = error_message(exc)[:300]
        game.price_checked_at = utcnow()
        return None
    check = new_check(game, product)
    db.add(check)
    game.pricecharting_id = check.product_id
    game.price_checked_at = check.checked_at
    game.price_error = None
    return check


@dataclass
class PriceJobStatus:
    running: bool = False
    mode: str | None = None
    total: int = 0
    done: int = 0
    found: int = 0
    not_found: int = 0
    current: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    cancelled: bool = False
    errors: list[str] = field(default_factory=list)


class PriceChecker:
    """Checks the prices of many items in the background, one job at a time."""

    def __init__(self, session_factory: sessionmaker, client: PriceCharting, refresh_days: int):
        self.session_factory = session_factory
        self.client = client
        self.refresh_days = refresh_days
        self.status = PriceJobStatus()
        self._task: asyncio.Task | None = None
        self._cancel = False

    def due_filter(self):
        """Items never checked, or checked more than refresh_days ago."""
        never = Game.price_checked_at.is_(None)
        if self.refresh_days <= 0:
            return never
        return never | (Game.price_checked_at < utcnow() - timedelta(days=self.refresh_days))

    def status_dict(self) -> dict:
        return asdict(self.status)

    def start(self, mode: str) -> int:
        if not self.client.enabled:
            raise ValueError("Set PRICECHARTING_TOKEN to look up prices")
        if self.status.running:
            raise RuntimeError("A price check is already running")
        with self.session_factory() as db:
            stmt = select(Game.id).where(*PRICED).order_by(Game.title, Game.id)
            if mode == "due":
                stmt = stmt.where(self.due_filter())
            game_ids = list(db.scalars(stmt))
        self._cancel = False
        self.status = PriceJobStatus(
            running=True, mode=mode, total=len(game_ids), started_at=datetime.now(timezone.utc).isoformat(),
        )
        self._task = asyncio.create_task(self._run(game_ids))
        return len(game_ids)

    def cancel(self) -> None:
        self._cancel = True

    async def _run(self, game_ids: list[int]) -> None:
        try:
            for game_id in game_ids:
                if self._cancel:
                    self.status.cancelled = True
                    break
                await self._check(game_id)
                self.status.done += 1
        finally:
            self.status.running = False
            self.status.current = None
            self.status.finished_at = datetime.now(timezone.utc).isoformat()

    async def _check(self, game_id: int) -> None:
        with self.session_factory() as db:
            game = db.get(Game, game_id, options=[selectinload(Game.platform)])
            if not game:
                return
            self.status.current = game.title
            try:
                check = await check_game(self.client, db, game)
            except Exception as exc:  # one bad item must not stop the batch
                check, game.price_error = None, error_message(exc)[:300]
            if check:
                self.status.found += 1
            else:
                self.status.not_found += 1
                if len(self.status.errors) < 20:
                    self.status.errors.append(f"{game.title}: {game.price_error}")
            try:
                db.commit()
            except (StaleDataError, IntegrityError):  # deleted meanwhile
                db.rollback()

    async def run_forever(self, first_delay: float = 60, every: float = 3600) -> None:
        """Automatic checks: every hour, look up the items that are due (refresh_days > 0)."""
        await asyncio.sleep(first_delay)
        while True:
            if self.client.enabled and self.refresh_days > 0 and not self.status.running:
                with self.session_factory() as db:
                    due = db.scalar(select(func.count(Game.id)).where(*PRICED, self.due_filter()))
                if due:
                    self.start("due")
            await asyncio.sleep(every)
