import time

from .base import MetadataProvider, SearchResult, year_from

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
API_URL = "https://api.igdb.com/v4"
IMAGE_URL = "https://images.igdb.com/igdb/image/upload/{size}/{image_id}.jpg"


def _join(names) -> str | None:
    return ", ".join(n for n in names if n) or None


def _companies(involved: list[dict], role: str) -> str | None:
    """Names of the companies with the given role ("publisher" or "developer")."""
    return _join((c.get("company") or {}).get("name") for c in involved if c.get(role))


class IGDBProvider(MetadataProvider):
    """IGDB (https://api-docs.igdb.com). Needs a Twitch developer app: client id + secret."""

    name = "igdb"
    label = "IGDB"
    image_hosts = ("images.igdb.com",)

    def __init__(self, http, client_id: str, client_secret: str):
        super().__init__(http)
        self.client_id = client_id
        self.client_secret = client_secret
        self._token: str | None = None
        self._token_expires = 0.0

    @property
    def enabled(self) -> bool:
        return bool(self.client_id and self.client_secret)

    async def _get_token(self) -> str:
        if self._token and time.monotonic() < self._token_expires - 60:
            return self._token
        res = await self.http.post(TOKEN_URL, params={
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
        })
        res.raise_for_status()
        data = res.json()
        self._token = data["access_token"]
        self._token_expires = time.monotonic() + data.get("expires_in", 3600)
        return self._token

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        token = await self._get_token()
        safe_query = query.replace('"', "")
        body = (
            f'search "{safe_query}"; '
            "fields name, first_release_date, summary, cover.image_id, platforms.name, genres.name, "
            "collection.name, involved_companies.publisher, involved_companies.developer, "
            "involved_companies.company.name; "
            f"limit {limit};"
        )
        res = await self.http.post(
            f"{API_URL}/games",
            content=body,
            headers={"Client-ID": self.client_id, "Authorization": f"Bearer {token}"},
        )
        res.raise_for_status()
        results = []
        for game in res.json():
            image_id = (game.get("cover") or {}).get("image_id")
            companies = game.get("involved_companies", [])
            results.append(SearchResult(
                provider=self.name,
                external_id=str(game["id"]),
                title=game.get("name", ""),
                release_year=year_from(game.get("first_release_date")),
                platforms=[p["name"] for p in game.get("platforms", []) if "name" in p],
                summary=game.get("summary"),
                publisher=_companies(companies, "publisher"),
                developer=_companies(companies, "developer"),
                genre=_join(g.get("name") for g in game.get("genres", [])),
                series=(game.get("collection") or {}).get("name"),
                cover_urls=[IMAGE_URL.format(size="t_cover_big_2x", image_id=image_id)] if image_id else [],
                thumb_url=IMAGE_URL.format(size="t_cover_small", image_id=image_id) if image_id else None,
            ))
        return results
