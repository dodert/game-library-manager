"""Bulk metadata/cover lookup ("scraping") over the library.

One job runs at a time in the background. For each game it searches every enabled provider
by title, keeps the results whose title matches closely enough, and takes the cover (and any
empty summary/year) from the best one. Games are marked with scraped_at so "missing" mode
only visits games that were never looked up.
"""
import asyncio
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import selectinload, sessionmaker

from .images import ImageError, save_first_cover
from .models import Game
from .providers import MetadataProvider, SearchResult
from .providers.steam import cover_candidates as steam_cover_candidates
from .text import clean_html

# Preferred source when two results match equally well
PROVIDER_ORDER = ["igdb", "screenscraper", "steamgriddb", "steam"]
MIN_SCORE = 0.8
PLATFORM_BONUS = 0.1
DELAY_SECONDS = 0.5  # between games, to stay well inside the providers' rate limits


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"[™®©]", "", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def match_score(game_title: str, platform: str, result: SearchResult) -> float:
    a, b = _norm(game_title), _norm(result.title)
    if not a or not b:
        return 0.0
    score = SequenceMatcher(None, a, b).ratio()
    p = _norm(platform)
    if p and any(p in _norm(x) or _norm(x) in p for x in result.platforms if _norm(x)):
        score += PLATFORM_BONUS
    return score


def rank_results(game_title: str, platform: str, results: list[SearchResult]) -> list[SearchResult]:
    """Results that match the title, best first."""
    scored = [(match_score(game_title, platform, r), r) for r in results]
    good = [(s, r) for s, r in scored if s >= MIN_SCORE]
    order = {name: i for i, name in enumerate(PROVIDER_ORDER)}
    good.sort(key=lambda sr: (-round(sr[0], 2), order.get(sr[1].provider, len(order))))
    return [r for _, r in good]


MAX_COVER_OPTIONS = 60


def cover_options(game_title: str, platform: str, results: list[SearchResult],
                  providers: dict[str, MetadataProvider]) -> list[dict]:
    """Every cover the results offer, one entry per distinct image: title matches first, then the rest."""
    order = {name: i for i, name in enumerate(PROVIDER_ORDER)}
    scored = sorted(
        ((match_score(game_title, platform, r), r) for r in results if r.cover_urls),
        key=lambda sr: (-(round(sr[0], 2) >= MIN_SCORE), -round(sr[0], 2), order.get(sr[1].provider, len(order))),
    )
    options = []
    for score, r in scored:
        provider = providers.get(r.provider)
        base = {"provider": r.provider, "title": r.title, "platforms": r.platforms,
                "release_year": r.release_year, "matches": score >= MIN_SCORE}
        if provider and provider.cover_urls_are_fallbacks:
            options.append(base | {"urls": r.cover_urls, "thumb_url": r.thumb_url or r.cover_urls[0]})
        else:
            for i, url in enumerate(r.cover_urls):
                thumb = r.cover_thumbs[i] if i < len(r.cover_thumbs) else (r.thumb_url if i == 0 else None)
                options.append(base | {"urls": [url], "thumb_url": thumb or url})
    return options[:MAX_COVER_OPTIONS]


# Game fields a lookup can fill (only when empty), and the text limit of each column
DETAIL_FIELDS = {"summary": None, "release_year": None, "publisher": 150, "developer": 150, "genre": 150, "series": 150}


def fill_details(game: Game, matches: list[SearchResult]) -> bool:
    """Fill the game's empty detail fields from the best match that has each one. True if any was filled."""
    filled = False
    for name, limit in DETAIL_FIELDS.items():
        if getattr(game, name) not in (None, ""):
            continue
        value = next((getattr(r, name) for r in matches if getattr(r, name)), None)
        if name == "summary":
            value = clean_html(value)
        elif isinstance(value, str) and limit:
            value = value[:limit]
        if value:
            setattr(game, name, value)
            filled = True
    return filled


@dataclass
class ScrapeStatus:
    running: bool = False
    mode: str | None = None
    total: int = 0
    done: int = 0
    found: int = 0
    covers: int = 0
    details: int = 0  # games that got at least one empty field filled
    not_found: int = 0
    failed: int = 0
    sources: list[str] = field(default_factory=list)  # labels of the providers used
    want_covers: bool = True
    want_details: bool = True
    current: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    cancelled: bool = False
    errors: list[str] = field(default_factory=list)


class Scraper:
    def __init__(
        self,
        session_factory: sessionmaker,
        http: httpx.AsyncClient,
        providers: dict[str, MetadataProvider],
        covers_dir: Path,
        delay: float = DELAY_SECONDS,
    ):
        self.session_factory = session_factory
        self.http = http
        self.providers = providers
        self.covers_dir = covers_dir
        self.delay = delay
        self.status = ScrapeStatus()
        self._task: asyncio.Task | None = None
        self._cancel = False
        self._selected: list[MetadataProvider] = []

    @property
    def enabled_providers(self) -> list[MetadataProvider]:
        return [p for p in self.providers.values() if p.enabled]

    def status_dict(self) -> dict:
        return asdict(self.status)

    def start(self, mode: str, providers: list[str] | None = None, covers: bool = True, details: bool = True) -> None:
        if self.status.running:
            raise RuntimeError("A lookup is already running")
        enabled = {p.name: p for p in self.enabled_providers}
        unknown = [name for name in providers or [] if name not in enabled]
        if unknown:
            raise ValueError(f"Provider not available: {', '.join(unknown)}")
        selected = [enabled[name] for name in providers] if providers else list(enabled.values())
        if not selected:
            raise ValueError("No provider is enabled")
        with self.session_factory() as db:
            stmt = select(Game.id).order_by(Game.title, Game.id)
            if mode == "missing":
                stmt = stmt.where(Game.scraped_at.is_(None))
            game_ids = list(db.scalars(stmt))
        self._cancel = False
        self._selected = selected
        self.status = ScrapeStatus(
            running=True, mode=mode, total=len(game_ids), started_at=datetime.now(timezone.utc).isoformat(),
            sources=[p.label for p in selected], want_covers=covers, want_details=details,
        )
        self._task = asyncio.create_task(self._run(game_ids, replace_covers=mode == "all"))

    def cancel(self) -> None:
        self._cancel = True

    async def _run(self, game_ids: list[int], replace_covers: bool) -> None:
        try:
            for i, game_id in enumerate(game_ids):
                if self._cancel:
                    self.status.cancelled = True
                    break
                await self.scrape_game(game_id, replace_cover=replace_covers)
                self.status.done += 1
                self.status.current = None
                if self.delay and i + 1 < len(game_ids):
                    await asyncio.sleep(self.delay)
        finally:
            self.status.running = False
            self.status.current = None
            self.status.finished_at = datetime.now(timezone.utc).isoformat()

    async def scrape_game(self, game_id: int, replace_cover: bool) -> None:
        covers, details = self.status.want_covers, self.status.want_details
        with self.session_factory() as db:
            game = db.get(Game, game_id, options=[selectinload(Game.platform)])
            if not game:
                return
            self.status.current = game.title
            title, platform = game.title, game.platform.name
            try:
                results = await self._search(title)
                matches = rank_results(title, platform, results)
                cover = None
                if covers and (replace_cover or not game.cover_path):
                    cover = await self._download_cover(game, matches)
                if cover:
                    if game.cover_path:
                        (self.covers_dir / game.cover_path).unlink(missing_ok=True)
                    game.cover_path = cover
                    self.status.covers += 1
                if details and matches and fill_details(game, matches):
                    self.status.details += 1
                if matches or cover:
                    self.status.found += 1
                    game.scrape_error = None
                else:
                    self.status.not_found += 1
                    game.scrape_error = "Sin resultados"
            except Exception as exc:  # one bad game must not stop the batch
                self.status.failed += 1
                message = str(exc) or exc.__class__.__name__
                game.scrape_error = message[:300]
                if len(self.status.errors) < 20:
                    self.status.errors.append(f"{title}: {message}")
            game.scraped_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.commit()

    async def _search(self, title: str) -> list[SearchResult]:
        providers = self._selected or self.enabled_providers
        outcomes = await asyncio.gather(*(p.search(title) for p in providers), return_exceptions=True)
        results, errors = [], []
        for provider, outcome in zip(providers, outcomes):
            if isinstance(outcome, Exception):
                errors.append(f"{provider.label}: {outcome or outcome.__class__.__name__}")
            else:
                results.extend(outcome)
        if errors and len(errors) == len(providers):
            raise RuntimeError("; ".join(errors))
        return results

    async def _download_cover(self, game: Game, matches: list[SearchResult]) -> str | None:
        candidates: list[tuple[MetadataProvider, list[str]]] = []
        steam = self.providers.get("steam")
        if game.steam_appid and steam and steam in (self._selected or self.enabled_providers):
            candidates.append((steam, steam_cover_candidates(game.steam_appid)))
        for result in matches:
            provider = self.providers.get(result.provider)
            if provider and result.cover_urls:
                candidates.append((provider, result.cover_urls))
        for provider, urls in candidates:
            try:
                return await save_first_cover(self.http, provider, urls, self.covers_dir, game.id)
            except ImageError:
                continue
        return None
