import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

JPEG = b"\xff\xd8\xff\xe0fakejpeg"


def handler(request: httpx.Request) -> httpx.Response:
    url = request.url
    host, path = url.host, url.path
    if host == "id.twitch.tv":
        return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
    if host == "api.igdb.com":
        assert request.headers["Client-ID"] == "cid"
        assert request.headers["Authorization"] == "Bearer tok"
        assert b'search "Hades"' in request.content
        return httpx.Response(200, json=[{
            "id": 113112, "name": "Hades", "first_release_date": 1600300800,
            "summary": "Roguelike", "cover": {"image_id": "co39vc"},
            "platforms": [{"name": "PC (Microsoft Windows)"}, {"name": "Nintendo Switch"}],
        }])
    if host == "www.steamgriddb.com" and path.startswith("/api/v2/search/autocomplete/"):
        assert request.headers["Authorization"] == "Bearer sgdb"
        return httpx.Response(200, json={"success": True, "data": [{"id": 5, "name": "Hades", "release_date": 1600300800}]})
    if host == "www.steamgriddb.com" and path == "/api/v2/grids/game/5":
        assert url.params["dimensions"] == "600x900"
        return httpx.Response(200, json={"success": True, "data": [
            {"url": "https://cdn2.steamgriddb.com/grid/a.png", "thumb": "https://cdn2.steamgriddb.com/thumb/a.png"}
        ]})
    if host == "store.steampowered.com":
        return httpx.Response(200, json={"total": 1, "items": [
            {"id": 1145360, "name": "Hades", "tiny_image": "https://shared.cloudflare.steamstatic.com/x.jpg"}
        ]})
    if host == "api.steampowered.com":
        assert url.params["key"] == "skey" and url.params["steamid"] == "765"
        return httpx.Response(200, json={"response": {"game_count": 2, "games": [
            {"appid": 1145360, "name": "Hades"}, {"appid": 620, "name": "Portal 2"},
        ]}})
    if host == "cdn.cloudflare.steamstatic.com":
        if path.endswith("/620/library_600x900.jpg"):
            return httpx.Response(404)
        return httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})
    if host == "api.screenscraper.fr":
        assert url.params["devid"] == "dev" and url.params["recherche"] == "Hades"
        return httpx.Response(200, json={"response": {"jeux": [{
            "id": "300",
            "noms": [{"region": "us", "text": "Hades US"}, {"region": "eu", "text": "Hades"}],
            "systeme": {"id": "225", "text": "Switch"},
            "dates": [{"region": "eu", "text": "2020-09-17"}],
            "synopsis": [{"langue": "en", "text": "EN"}, {"langue": "es", "text": "ES"}],
            "editeur": {"id": "1", "text": "Supergiant Games"},
            "developpeur": {"id": "1", "text": "Supergiant Games"},
            "genres": [{"id": "1", "noms": [{"langue": "en", "text": "Action"}, {"langue": "es", "text": "Acción"}]},
                       {"id": "2", "noms": [{"langue": "en", "text": "Roguelike"}]}],
            "medias": [
                {"type": "box-2D", "region": "us", "url": "https://neoclone.screenscraper.fr/api2/mediaJeu.php?devid=dev&devpassword=secret&jeuid=300&media=box-2D(us)"},
                {"type": "box-2D", "region": "eu", "url": "https://neoclone.screenscraper.fr/api2/mediaJeu.php?devid=dev&devpassword=secret&jeuid=300&media=box-2D(eu)"},
                {"type": "ss", "region": "eu", "url": "https://neoclone.screenscraper.fr/ss.png"},
            ],
        }]}})
    if host == "neoclone.screenscraper.fr":
        assert url.params["devpassword"] == "secret"
        return httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})
    if host == "images.igdb.com":
        return httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})
    if host == "evil.example.com":
        return httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})
    return httpx.Response(500, text=f"unexpected {url}")


ALL_KEYS = dict(
    igdb_client_id="cid", igdb_client_secret="csecret", steamgriddb_api_key="sgdb",
    steam_api_key="skey", steam_id="765", screenscraper_dev_id="dev", screenscraper_dev_password="secret",
)


def make_client(tmp_path, **settings):
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return TestClient(create_app(Settings(data_dir=tmp_path, **settings), http_client=http))


@pytest.fixture
def client(tmp_path):
    return make_client(tmp_path, **ALL_KEYS)


def pc_id(client):
    return next(p["id"] for p in client.get("/api/platforms").json() if p["name"] == "PC")


def test_providers_enabled_by_credentials(tmp_path):
    bare = make_client(tmp_path)
    enabled = {p["name"]: p["enabled"] for p in bare.get("/api/providers").json()}
    assert enabled == {"igdb": False, "steamgriddb": False, "steam": True, "screenscraper": False}


def test_search_all_providers(client):
    res = client.get("/api/metadata/search", params={"q": "Hades"}).json()
    assert res["errors"] == {}
    by_provider = {r["provider"]: r for r in res["results"]}
    assert set(by_provider) == {"igdb", "steamgriddb", "steam", "screenscraper"}

    igdb = by_provider["igdb"]
    assert igdb["release_year"] == 2020
    assert igdb["cover_urls"] == ["https://images.igdb.com/igdb/image/upload/t_cover_big_2x/co39vc.jpg"]
    assert "Nintendo Switch" in igdb["platforms"]

    assert by_provider["steamgriddb"]["cover_urls"] == ["https://cdn2.steamgriddb.com/grid/a.png"]
    assert by_provider["steam"]["cover_urls"][0].endswith("/1145360/library_600x900.jpg")

    ss = by_provider["screenscraper"]
    assert ss["title"] == "Hades" and ss["summary"] == "ES" and ss["release_year"] == 2020
    assert (ss["publisher"], ss["developer"], ss["genre"]) == ("Supergiant Games", "Supergiant Games", "Acción, Roguelike")
    assert "media=box-2D%28eu%29" in ss["cover_urls"][0]
    assert all("secret" not in u for u in ss["cover_urls"] + [ss["thumb_url"]])


def test_search_reports_provider_errors(tmp_path):
    def failing(request):
        if request.url.host == "id.twitch.tv":
            return httpx.Response(401, json={"message": "invalid client secret"})
        return handler(request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(failing))
    client = TestClient(create_app(Settings(data_dir=tmp_path, igdb_client_id="cid", igdb_client_secret="x"), http_client=http))
    res = client.get("/api/metadata/search", params={"q": "Hades"}).json()
    assert "igdb" in res["errors"]
    assert any(r["provider"] == "steam" for r in res["results"])


def test_fetch_cover_with_fallback_and_credentials(client):
    game = client.post("/api/games", json={"title": "Portal 2", "platform_id": pc_id(client), "format": "digital"}).json()
    urls = [
        "https://cdn.cloudflare.steamstatic.com/steam/apps/620/library_600x900.jpg",
        "https://cdn.cloudflare.steamstatic.com/steam/apps/620/header.jpg",
    ]
    res = client.post(f"/api/games/{game['id']}/cover/fetch", json={"provider": "steam", "urls": urls})
    assert res.status_code == 200
    assert client.get(res.json()["cover_url"]).content == JPEG

    ss_url = client.get("/api/metadata/search", params={"q": "Hades", "provider": "screenscraper"}).json()["results"][0]["cover_urls"][0]
    res = client.post(f"/api/games/{game['id']}/cover/fetch", json={"provider": "screenscraper", "urls": [ss_url]})
    assert res.status_code == 200


def test_cover_fetch_rejects_foreign_hosts(client):
    game = client.post("/api/games", json={"title": "X", "platform_id": pc_id(client), "format": "digital"}).json()
    res = client.post(f"/api/games/{game['id']}/cover/fetch", json={"provider": "steam", "urls": ["https://evil.example.com/a.jpg"]})
    assert res.status_code == 502
    res = client.get("/api/metadata/image", params={"provider": "igdb", "url": "http://images.igdb.com/a.jpg"})
    assert res.status_code == 502


def test_image_proxy(client):
    res = client.get("/api/metadata/image", params={"provider": "igdb", "url": "https://images.igdb.com/igdb/image/upload/t_cover_small/co39vc.jpg"})
    assert res.status_code == 200 and res.content == JPEG


def test_steam_import(client):
    res = client.post("/api/import/steam").json()
    assert res == {"imported": 2, "skipped": 0}
    games = {g["title"]: g for g in client.get("/api/games").json()["items"]}
    assert games["Hades"]["store"] == "Steam" and games["Hades"]["format"] == "digital"
    assert games["Hades"]["cover_url"]  # covers downloaded in the background task
    assert games["Portal 2"]["cover_url"]  # fell back to header.jpg
    assert client.post("/api/import/steam").json() == {"imported": 0, "skipped": 2}


def test_steam_import_needs_credentials(tmp_path):
    assert make_client(tmp_path).post("/api/import/steam").status_code == 400


def test_provider_connection_test(client):
    res = client.post("/api/providers/igdb/test").json()
    assert res["status"] == "ok" and res["results"] == 1 and res["ms"] >= 0
    steam = client.post("/api/providers/steam/test").json()
    assert steam["status"] == "ok" and steam["library_games"] == 2
    assert client.post("/api/providers/nope/test").status_code == 404


def test_provider_connection_test_unconfigured_and_errors(tmp_path):
    bare = make_client(tmp_path / "bare")
    assert bare.post("/api/providers/igdb/test").json()["status"] == "not_configured"
    assert bare.post("/api/providers/steam/test").json()["library_games"] is None

    def failing(request):
        if request.url.host in ("www.steamgriddb.com", "api.steampowered.com"):
            return httpx.Response(401, json={"message": "bad key"})
        return handler(request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(failing))
    client = TestClient(create_app(Settings(data_dir=tmp_path / "bad", **ALL_KEYS), http_client=http))
    sgdb = client.post("/api/providers/steamgriddb/test").json()
    assert sgdb == {"status": "error", "error": "HTTP 401", "results": None, "ms": sgdb["ms"], "library_games": None}
    steam = client.post("/api/providers/steam/test").json()
    # Store search works, the Web API key doesn't; the key never shows in the error
    assert steam["status"] == "error" and steam["error"] == "HTTP 401" and steam["results"] == 1
    assert "skey" not in str(steam)
