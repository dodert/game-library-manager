import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

SGDB = "https://cdn2.steamgriddb.com/grid"


def handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if request.url.host == "store.steampowered.com":
        return httpx.Response(200, json={"items": [
            {"id": 1145360, "name": "Hades", "tiny_image": "https://cdn.cloudflare.steamstatic.com/steam/apps/1145360/capsule.jpg"},
            {"id": 1145350, "name": "Hades II", "tiny_image": None},
        ]})
    if "/search/autocomplete/" in url:
        return httpx.Response(200, json={"data": [{"id": 7, "name": "Hades"}]})
    if "/grids/game/7" in url:
        return httpx.Response(200, json={"data": [
            {"url": f"{SGDB}/a.png", "thumb": f"{SGDB}/thumb/a.png"},
            {"url": f"{SGDB}/b.png", "thumb": f"{SGDB}/thumb/b.png"},
        ]})
    return httpx.Response(500, text=f"unexpected {url}")


def test_cover_search_lists_every_cover_matches_first(tmp_path):
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    app = create_app(Settings(data_dir=tmp_path, steamgriddb_api_key="k"), http_client=http)
    with TestClient(app) as client:
        res = client.get("/api/covers/search", params={"q": "Hades", "platform": "Nintendo Switch"}).json()
    assert res["errors"] == {}
    opts = res["options"]
    # SteamGridDB: one option per grid, each with its own thumbnail
    sgdb = [o for o in opts if o["provider"] == "steamgriddb"]
    assert [o["urls"] for o in sgdb] == [[f"{SGDB}/a.png"], [f"{SGDB}/b.png"]]
    assert sgdb[1]["thumb_url"] == f"{SGDB}/thumb/b.png"
    # Steam: portrait art and header are fallbacks of one cover, so one option per game
    steam = [o for o in opts if o["provider"] == "steam"]
    assert len(steam) == 2 and len(steam[0]["urls"]) == 2
    # Exact title matches come before "Hades II"
    assert [o["matches"] for o in opts] == [True, True, True, False]
    assert opts[-1]["title"] == "Hades II"
