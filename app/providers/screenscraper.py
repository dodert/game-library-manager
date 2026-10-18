from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .base import MetadataProvider, SearchResult, year_from

API_URL = "https://api.screenscraper.fr/api2"
SOFTNAME = "game-library-manager"
REGION_PRIORITY = ("eu", "sp", "fr", "wor", "us", "ss", "jp")
# ScreenScraper media URLs carry the API credentials; they are stripped before URLs reach
# the browser and added back when the server downloads the image.
CREDENTIAL_PARAMS = ("devid", "devpassword", "ssid", "sspassword")


def _strip_credentials(url: str) -> str:
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in CREDENTIAL_PARAMS]
    return urlunsplit(parts._replace(query=urlencode(query)))


def _pick(entries: list[dict], key: str = "region") -> str | None:
    """Pick the text of the entry with the best region (Europe/Spain first)."""
    if not entries:
        return None
    by_region = {e.get(key): e.get("text") for e in entries}
    for region in REGION_PRIORITY:
        if by_region.get(region):
            return by_region[region]
    return entries[0].get("text")


class ScreenScraperProvider(MetadataProvider):
    """ScreenScraper (https://www.screenscraper.fr). Needs developer credentials + a user account."""

    name = "screenscraper"
    label = "ScreenScraper"
    image_hosts = ("screenscraper.fr",)

    def __init__(self, http, dev_id: str, dev_password: str, user: str = "", password: str = ""):
        super().__init__(http)
        self.dev_id = dev_id
        self.dev_password = dev_password
        self.user = user
        self.password = password

    @property
    def enabled(self) -> bool:
        return bool(self.dev_id and self.dev_password)

    def authorize_url(self, url: str) -> str:
        parts = urlsplit(_strip_credentials(url))
        query = parse_qsl(parts.query, keep_blank_values=True) + [
            ("devid", self.dev_id), ("devpassword", self.dev_password),
            ("ssid", self.user), ("sspassword", self.password),
        ]
        return urlunsplit(parts._replace(query=urlencode(query)))

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        params = {
            "devid": self.dev_id,
            "devpassword": self.dev_password,
            "softname": SOFTNAME,
            "output": "json",
            "recherche": query,
        }
        if self.user:
            params |= {"ssid": self.user, "sspassword": self.password}
        res = await self.http.get(f"{API_URL}/jeuRecherche.php", params=params)
        res.raise_for_status()
        results = []
        for game in res.json().get("response", {}).get("jeux", [])[:limit]:
            if not game.get("id"):
                continue
            boxes = [m | {"url": _strip_credentials(m["url"])} for m in game.get("medias", []) if m.get("type") == "box-2D" and m.get("url")]
            boxes.sort(key=lambda m: REGION_PRIORITY.index(m["region"]) if m.get("region") in REGION_PRIORITY else 99)
            synopsis = {s.get("langue"): s.get("text") for s in game.get("synopsis", [])}
            system = (game.get("systeme") or {}).get("text")
            results.append(SearchResult(
                provider=self.name,
                external_id=str(game["id"]),
                title=_pick(game.get("noms", [])) or "",
                release_year=year_from(_pick(game.get("dates", []))),
                platforms=[system] if system else [],
                summary=synopsis.get("es") or synopsis.get("en"),
                cover_urls=[m["url"] for m in boxes],
                thumb_url=boxes[0]["url"] if boxes else None,
            ))
        return results
