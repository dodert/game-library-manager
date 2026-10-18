from .base import MetadataProvider, SearchResult

STORE_SEARCH_URL = "https://store.steampowered.com/api/storesearch/"
OWNED_GAMES_URL = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
CDN_URL = "https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/{file}"


def cover_candidates(appid: int | str) -> list[str]:
    """Portrait library art first, then the wide store header as a fallback."""
    return [CDN_URL.format(appid=appid, file=f) for f in ("library_600x900.jpg", "header.jpg")]


class SteamProvider(MetadataProvider):
    """Steam store search (no key needed). Library import needs a Web API key + SteamID64."""

    name = "steam"
    label = "Steam"
    image_hosts = ("steamstatic.com", "steampowered.com", "akamaihd.net")

    def __init__(self, http, api_key: str = "", steam_id: str = ""):
        super().__init__(http)
        self.api_key = api_key
        self.steam_id = steam_id

    @property
    def can_import(self) -> bool:
        return bool(self.api_key and self.steam_id)

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        res = await self.http.get(STORE_SEARCH_URL, params={"term": query, "l": "english", "cc": "US"})
        res.raise_for_status()
        return [
            SearchResult(
                provider=self.name,
                external_id=str(item["id"]),
                title=item.get("name", ""),
                platforms=["PC"],
                cover_urls=cover_candidates(item["id"]),
                thumb_url=item.get("tiny_image"),
            )
            for item in res.json().get("items", [])[:limit]
        ]

    async def owned_games(self) -> list[dict]:
        res = await self.http.get(OWNED_GAMES_URL, params={
            "key": self.api_key,
            "steamid": self.steam_id,
            "include_appinfo": 1,
            "format": "json",
        })
        res.raise_for_status()
        return res.json().get("response", {}).get("games", [])
