import pytest
from fastapi.testclient import TestClient

from app import __version__
from app.config import Settings
from app.main import create_app

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(Settings(data_dir=tmp_path, database_url="")))


def platform_id(client, name="PlayStation 5"):
    return next(p["id"] for p in client.get("/api/platforms").json() if p["name"] == name)


def test_health_and_seeded_platforms(client):
    assert client.get("/api/health").json()["status"] == "ok"
    names = {p["name"] for p in client.get("/api/platforms").json()}
    assert {"PC", "Nintendo Switch", "PlayStation 5"} <= names


def test_game_crud(client):
    pid = platform_id(client)
    res = client.post("/api/games", json={"title": "Astro Bot", "platform_id": pid, "format": "physical"})
    assert res.status_code == 201
    game = res.json()
    assert game["platform"]["name"] == "PlayStation 5"
    assert game["status"] == "owned"

    res = client.patch(f"/api/games/{game['id']}", json={"completion": "completed", "purchase_price": 59.99})
    assert res.json()["completion"] == "completed"
    assert res.json()["purchase_price"] == 59.99

    assert client.delete(f"/api/games/{game['id']}").status_code == 204
    assert client.get(f"/api/games/{game['id']}").status_code == 404


def test_unknown_platform_rejected(client):
    res = client.post("/api/games", json={"title": "X", "platform_id": 9999, "format": "digital"})
    assert res.status_code == 422


def test_filters_search_and_stats(client):
    ps5, pc = platform_id(client), platform_id(client, "PC")
    client.post("/api/games", json={"title": "Elden Ring", "platform_id": pc, "format": "digital", "store": "Steam"})
    client.post("/api/games", json={"title": "Astro Bot", "platform_id": ps5, "format": "physical", "barcode": "711719"})
    client.post("/api/games", json={"title": "Hades II", "platform_id": pc, "format": "digital", "status": "wishlist"})

    assert client.get("/api/games", params={"format": "digital"}).json()["total"] == 2
    assert client.get("/api/games", params={"q": "elden"}).json()["items"][0]["title"] == "Elden Ring"
    assert client.get("/api/games", params={"q": "711719"}).json()["total"] == 1
    assert client.get("/api/games", params={"status": "wishlist"}).json()["total"] == 1
    titles = [g["title"] for g in client.get("/api/games", params={"sort": "-title"}).json()["items"]]
    assert titles == ["Hades II", "Elden Ring", "Astro Bot"]

    stats = client.get("/api/stats").json()
    # The wishlist game (Hades II) counts in the total but not in the collection figures
    assert stats["total"] == 3 and stats["collection"] == 2
    assert stats["by_platform"] == {"PC": 1, "PlayStation 5": 1}
    assert stats["by_format"] == {"digital": 1, "physical": 1}
    assert stats["by_status"] == {"owned": 2, "wishlist": 1}
    assert stats["loaned"] == 0

    both = client.get("/api/games", params=[("status", "owned"), ("status", "wishlist")]).json()
    assert both["total"] == 3


def test_cover_upload(client, tmp_path):
    game = client.post("/api/games", json={"title": "Celeste", "platform_id": platform_id(client, "PC"), "format": "digital"}).json()
    res = client.put(f"/api/games/{game['id']}/cover", files={"file": ("c.png", PNG_1PX, "image/png")})
    assert res.status_code == 200
    url = res.json()["cover_url"]
    assert client.get(url).content == PNG_1PX

    bad = client.put(f"/api/games/{game['id']}/cover", files={"file": ("c.txt", b"x", "text/plain")})
    assert bad.status_code == 415


def test_index_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "My library" in res.text


def test_about_and_versioned_assets(tmp_path):
    client = TestClient(create_app(Settings(data_dir=tmp_path, git_sha="de2880af3e16", git_ref="main", build_date="2026-10-18T13:22:00Z")))
    about = client.get("/api/about").json()
    assert about["version"] == __version__ and about["commit"] == "de2880af3e16" and about["ref"] == "main"
    assert about["database"] == "sqlite" and about["schema"] == "0006"
    page = client.get("/")
    assert page.headers["cache-control"] == "no-cache"
    assert f"/static/app.js?v={__version__}-de2880a" in page.text and "{{" not in page.text


def test_reset_library(client, tmp_path):
    pc = next(p["id"] for p in client.get("/api/platforms").json() if p["name"] == "PC")
    game = client.post("/api/games", json={"title": "Ico", "platform_id": pc, "format": "physical"}).json()
    client.put(f"/api/games/{game['id']}/cover", files={"file": ("c.png", PNG_1PX, "image/png")})
    client.post("/api/platforms", json={"name": "Sin plataforma"})
    seeded = len(client.get("/api/platforms").json()) - 1

    assert client.post("/api/reset", json={"confirm": "si"}).status_code == 400
    res = client.post("/api/reset", json={"confirm": "BORRAR"}).json()
    assert res == {"games_deleted": 1, "platforms_deleted": 1}
    assert client.get("/api/games").json()["total"] == 0
    assert len(client.get("/api/platforms").json()) == seeded
    assert not any((tmp_path / "covers").iterdir())


def test_image_version_overrides_package_version(tmp_path):
    client = TestClient(create_app(Settings(data_dir=tmp_path, app_version="0.5.0-feat-bulk-scrape.27")))
    assert client.get("/api/about").json()["version"] == "0.5.0-feat-bulk-scrape.27"
    assert client.get("/api/health").json()["version"] == "0.5.0-feat-bulk-scrape.27"
    assert "/static/app.js?v=0.5.0-feat-bulk-scrape.27" in client.get("/").text


def test_sort_by_table_columns(client):
    ps5, pc = platform_id(client), platform_id(client, "PC")
    client.post("/api/games", json={"title": "A", "platform_id": pc, "format": "digital", "purchase_price": 30, "rating": 7})
    client.post("/api/games", json={"title": "B", "platform_id": ps5, "format": "physical", "purchase_price": 10})
    client.post("/api/games", json={"title": "C", "platform_id": ps5, "format": "digital", "rating": 9})

    def order(sort):
        return [g["title"] for g in client.get("/api/games", params={"sort": sort}).json()["items"]]

    assert order("platform") == ["A", "B", "C"]  # PC < PlayStation 5, then by id
    assert order("-platform") == ["B", "C", "A"]
    assert order("purchase_price") == ["B", "A", "C"]  # no price goes last
    assert order("-purchase_price") == ["A", "B", "C"]
    assert order("-rating") == ["C", "A", "B"]
    assert client.get("/api/games", params={"sort": "nope"}).status_code == 422


def test_favicon_and_touch_icon(client):
    res = client.get("/favicon.ico")
    assert res.status_code == 200 and res.headers["content-type"] == "image/x-icon"
    assert res.content[:4] == b"\x00\x00\x01\x00"  # ICO header
    assert client.get("/apple-touch-icon.png").content[:8] == b"\x89PNG\r\n\x1a\n"
    html = client.get("/").text
    assert 'rel="icon"' in html and 'rel="apple-touch-icon"' in html and 'rel="manifest"' in html
    assert client.get("/static/icons/manifest.webmanifest").json()["icons"]
