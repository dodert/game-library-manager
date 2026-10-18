import asyncio
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.images import MAX_IMAGE_BYTES
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(Settings(data_dir=tmp_path, database_url="")))


def new_game(client, title="Astro Bot"):
    pid = client.get("/api/platforms").json()[0]["id"]
    return client.post("/api/games", json={"title": title, "platform_id": pid, "format": "physical"}).json()


def test_provider_errors_do_not_leak_credentials(tmp_path):
    def handler(request):
        return httpx.Response(403, text="denied")

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    app = create_app(Settings(
        data_dir=tmp_path, igdb_client_id="cid", igdb_client_secret="IGDB-SECRET",
        screenscraper_dev_id="dev", screenscraper_dev_password="SS-SECRET",
        steam_api_key="STEAM-SECRET", steam_id="1",
    ), http_client=http)
    with TestClient(app) as client:
        search = client.get("/api/metadata/search", params={"q": "Hades"})
        steam = client.post("/api/import/steam")
    assert search.json()["errors"]["igdb"] == "HTTP 403"
    body = search.text + steam.text
    assert steam.status_code == 502
    for secret in ("IGDB-SECRET", "SS-SECRET", "STEAM-SECRET"):
        assert secret not in body


@pytest.mark.parametrize("field", ["title", "platform_id", "format", "status", "completion"])
def test_patch_rejects_null_required_fields(client, field):
    game = new_game(client)
    assert client.patch(f"/api/games/{game['id']}", json={field: None}).status_code == 422


def test_patch_rejects_text_longer_than_its_column(client):
    game = new_game(client)
    assert client.patch(f"/api/games/{game['id']}", json={"region": "x" * 21}).status_code == 422


def test_cover_upload_size_limit(client):
    game = new_game(client)
    big = b"\x89PNG" + b"0" * MAX_IMAGE_BYTES
    res = client.put(f"/api/games/{game['id']}/cover", files={"file": ("c.png", big, "image/png")})
    assert res.status_code == 413


def test_cross_site_writes_are_blocked(client):
    game = new_game(client)
    res = client.delete(f"/api/games/{game['id']}", headers={"Sec-Fetch-Site": "cross-site"})
    assert res.status_code == 403
    assert client.get(f"/api/games/{game['id']}", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 200
    assert client.delete(f"/api/games/{game['id']}", headers={"Sec-Fetch-Site": "same-origin"}).status_code == 204


def test_bulk_lookup_survives_a_game_deleted_mid_run(tmp_path):
    async def handler(request):
        await asyncio.sleep(0.3)
        return httpx.Response(200, json={"items": []})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    app = create_app(Settings(data_dir=tmp_path, scrape_delay=0), http_client=http)
    with TestClient(app) as client:
        ids = [new_game(client, t)["id"] for t in ("A", "B", "C")]
        assert client.post("/api/scrape", json={"mode": "missing"}).status_code == 202
        time.sleep(0.1)
        assert client.delete(f"/api/games/{ids[0]}").status_code == 204
        for _ in range(100):
            status = client.get("/api/scrape").json()
            if not status["running"]:
                break
            time.sleep(0.05)
    assert status["done"] == 3
    assert status["never_scraped"] == 0
