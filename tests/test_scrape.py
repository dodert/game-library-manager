import time

import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.providers import SearchResult
from app.scraper import rank_results

JPEG = b"\xff\xd8\xff\xe0fakejpeg"


def handler(request: httpx.Request) -> httpx.Response:
    host = request.url.host
    if host == "id.twitch.tv":
        return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
    if host == "api.igdb.com":
        if b'search "Hades"' in request.content:
            return httpx.Response(200, json=[
                {"id": 2, "name": "Hades II", "cover": {"image_id": "other"}},
                {"id": 1, "name": "Hades", "first_release_date": 1600300800, "summary": "Roguelike",
                 "cover": {"image_id": "co39vc"}, "platforms": [{"name": "PC (Microsoft Windows)"}],
                 "genres": [{"name": "Role-playing (RPG)"}, {"name": "Indie"}], "collection": {"name": "Hades"},
                 "involved_companies": [{"company": {"name": "Supergiant Games"}, "developer": True, "publisher": True}]},
            ])
        return httpx.Response(200, json=[{"id": 9, "name": "Something Else Entirely"}])
    if host == "store.steampowered.com":
        return httpx.Response(200, json={"total": 0, "items": []})
    if host == "images.igdb.com":
        assert "co39vc" in request.url.path  # never the Hades II cover
        return httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})
    return httpx.Response(500, text=f"unexpected {request.url}")


def run(client, mode, **options):
    assert client.post("/api/scrape", json={"mode": mode, **options}).status_code == 202
    for _ in range(200):
        status = client.get("/api/scrape").json()
        if not status["running"]:
            return status
        time.sleep(0.02)
    raise AssertionError("scrape did not finish")


def test_bulk_scrape_missing_then_all(tmp_path):
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    app = create_app(Settings(data_dir=tmp_path, igdb_client_id="cid", igdb_client_secret="x", scrape_delay=0), http_client=http)
    with TestClient(app) as client:
        pc = next(p["id"] for p in client.get("/api/platforms").json() if p["name"] == "PC")
        hades = client.post("/api/games", json={"title": "Hades", "platform_id": pc, "format": "digital"}).json()
        other = client.post("/api/games", json={"title": "Figura Amiibo Link", "platform_id": pc, "format": "physical",
                                                "summary": "Mi texto"}).json()
        before = client.get("/api/scrape").json()
        assert before["never_scraped"] == 2 and "IGDB" in before["providers"]

        status = run(client, "missing")
        assert (status["total"], status["found"], status["covers"], status["not_found"], status["failed"]) == (2, 1, 1, 1, 0)
        assert status["never_scraped"] == 0
        game = client.get(f"/api/games/{hades['id']}").json()
        assert game["cover_url"] and game["summary"] == "Roguelike" and game["release_year"] == 2020
        assert game["scraped_at"] and game["scrape_error"] is None
        miss = client.get(f"/api/games/{other['id']}").json()
        assert miss["cover_url"] is None and miss["scrape_error"] == "Sin resultados" and miss["summary"] == "Mi texto"

        assert run(client, "missing")["total"] == 0

        old_cover = tmp_path / "covers" / game["cover_url"].rsplit("/", 1)[1]
        status = run(client, "all")
        assert status["total"] == 2 and status["covers"] == 1
        new = client.get(f"/api/games/{hades['id']}").json()
        assert new["cover_url"] != game["cover_url"] and not old_cover.exists()


def test_rank_results_prefers_exact_title_and_platform():
    results = [
        SearchResult("steam", "1", "Super Mario Odyssey", platforms=["PC"]),
        SearchResult("igdb", "2", "Super Mario Odyssey", platforms=["Nintendo Switch"]),
        SearchResult("igdb", "3", "The Legend of Zelda: Tears of the Kingdom", platforms=["Nintendo Switch"]),
    ]
    ranked = rank_results("Super Mario Odyssey", "Nintendo Switch", results)
    assert [r.external_id for r in ranked] == ["2", "1"]
    assert rank_results("Figura Amiibo Link The Legend of Zelda", "Sin plataforma", results) == []


def make_client(tmp_path):
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    app = create_app(Settings(data_dir=tmp_path, igdb_client_id="cid", igdb_client_secret="x", scrape_delay=0), http_client=http)
    return TestClient(app)


def test_scrape_details_only_fills_empty_fields(tmp_path):
    with make_client(tmp_path) as client:
        pc = next(p["id"] for p in client.get("/api/platforms").json() if p["name"] == "PC")
        hades = client.post("/api/games", json={"title": "Hades", "platform_id": pc, "format": "digital",
                                                "genre": "Mi género"}).json()
        status = run(client, "missing", providers=["igdb"], covers=False, details=True)
        assert (status["covers"], status["details"], status["sources"]) == (0, 1, ["IGDB"])
        game = client.get(f"/api/games/{hades['id']}").json()
        assert game["cover_url"] is None
        assert (game["summary"], game["release_year"], game["publisher"], game["developer"], game["series"]) == (
            "Roguelike", 2020, "Supergiant Games", "Supergiant Games", "Hades")
        assert game["genre"] == "Mi género"  # already set, left alone


def test_scrape_only_uses_selected_providers(tmp_path):
    with make_client(tmp_path) as client:
        pc = next(p["id"] for p in client.get("/api/platforms").json() if p["name"] == "PC")
        client.post("/api/games", json={"title": "Hades", "platform_id": pc, "format": "digital"})
        # Steam alone finds nothing for Hades in the mock; IGDB is not asked
        status = run(client, "missing", providers=["steam"])
        assert (status["found"], status["not_found"], status["sources"]) == (0, 1, ["Steam"])

        assert client.post("/api/scrape", json={"mode": "all", "providers": ["steamgriddb"]}).status_code == 400
        assert client.post("/api/scrape", json={"mode": "all", "covers": False, "details": False}).status_code == 422
