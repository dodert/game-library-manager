from urllib.parse import quote

from .base import MetadataProvider, SearchResult, year_from

API_URL = "https://www.steamgriddb.com/api/v2"


class SteamGridDBProvider(MetadataProvider):
    """SteamGridDB (https://www.steamgriddb.com/api/v2). Needs a free API key."""

    name = "steamgriddb"
    label = "SteamGridDB"
    image_hosts = ("steamgriddb.com",)

    def __init__(self, http, api_key: str):
        super().__init__(http)
        self.api_key = api_key

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        res = await self.http.get(f"{API_URL}/search/autocomplete/{quote(query)}", headers=self._headers)
        res.raise_for_status()
        results = []
        for game in res.json().get("data", [])[:limit]:
            grids = await self.grids(game["id"])
            results.append(SearchResult(
                provider=self.name,
                external_id=str(game["id"]),
                title=game.get("name", ""),
                release_year=year_from(game.get("release_date")),
                cover_urls=[g["url"] for g in grids],
                thumb_url=grids[0].get("thumb") if grids else None,
                cover_thumbs=[g.get("thumb") or g["url"] for g in grids],
            ))
        return results

    async def grids(self, game_id: int) -> list[dict]:
        # 600x900 is the portrait "box art" size.
        res = await self.http.get(
            f"{API_URL}/grids/game/{game_id}", params={"dimensions": "600x900"}, headers=self._headers
        )
        if res.status_code == 404:
            return []
        res.raise_for_status()
        return res.json().get("data", [])[:10]
