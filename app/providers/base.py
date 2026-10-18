import re
from dataclasses import dataclass, field

import httpx

_URL_QUERY = re.compile(r"(https?://[^\s'\"?]+)\?[^\s'\"]*")


def error_message(exc: Exception) -> str:
    """Error text safe to show in the UI: providers put API keys and passwords in query strings."""
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    return _URL_QUERY.sub(r"\1", str(exc)) or exc.__class__.__name__


@dataclass
class SearchResult:
    provider: str
    external_id: str
    title: str
    release_year: int | None = None
    platforms: list[str] = field(default_factory=list)
    summary: str | None = None
    publisher: str | None = None
    developer: str | None = None
    genre: str | None = None
    series: str | None = None
    # Full-size cover candidates, best first; thumb is for the result list.
    cover_urls: list[str] = field(default_factory=list)
    thumb_url: str | None = None
    # Optional small version of each cover_urls entry, same order
    cover_thumbs: list[str] = field(default_factory=list)


class MetadataProvider:
    name: str = ""
    label: str = ""
    # Hosts covers are downloaded from (suffix match), used to validate cover URLs.
    image_hosts: tuple[str, ...] = ()
    # True when cover_urls are fallbacks for one image (try in order), not different covers to choose from
    cover_urls_are_fallbacks: bool = False

    def __init__(self, http: httpx.AsyncClient):
        self.http = http

    @property
    def enabled(self) -> bool:
        return True

    def authorize_url(self, url: str) -> str:
        """URL the server uses to download an image (adds credentials if the provider needs them)."""
        return url

    def allows_image_url(self, url: str) -> bool:
        from urllib.parse import urlsplit
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        return parts.scheme == "https" and any(host == h or host.endswith("." + h) for h in self.image_hosts)

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        raise NotImplementedError


def year_from(value: str | int | None) -> int | None:
    """Pull a 4-digit year from a date string ('2020-09-17', '17 Sep, 2020') or unix timestamp."""
    if value is None:
        return None
    if isinstance(value, int):
        from datetime import datetime, timezone
        return datetime.fromtimestamp(value, tz=timezone.utc).year
    import re
    match = re.search(r"(19|20)\d{2}", value)
    return int(match.group()) if match else None
