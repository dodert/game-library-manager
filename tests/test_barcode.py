import httpx
from fastapi.testclient import TestClient

from app.barcode import clean_title, guess_platform
from app.config import Settings
from app.main import create_app
from app.seed import DEFAULT_PLATFORMS

PLATFORMS = [name for name, _ in DEFAULT_PLATFORMS]
PRODUCTS = {"045496590420": "Super Mario Odyssey - Nintendo Switch", "711719541028": "Marvel's Spider-Man (PS4)"}


def upcitemdb(request: httpx.Request) -> httpx.Response:
    assert request.url.host == "api.upcitemdb.com" and request.url.path == "/prod/trial/lookup"
    code = request.url.params["upc"]
    if code == "99999999":
        return httpx.Response(429, json={"code": "TOO_FAST"})
    items = [{"ean": code, "title": PRODUCTS[code], "brand": "Nintendo"}] if code in PRODUCTS else []
    return httpx.Response(200, json={"code": "OK", "total": len(items), "offset": 0, "items": items})


def make_client(tmp_path):
    http = httpx.AsyncClient(transport=httpx.MockTransport(upcitemdb))
    return TestClient(create_app(Settings(data_dir=tmp_path), http_client=http))


def test_clean_title_and_platform():
    assert clean_title("Super Mario Odyssey - Nintendo Switch", PLATFORMS) == "Super Mario Odyssey"
    assert clean_title("Mario Kart 8 Deluxe (Nintendo Switch) PAL", PLATFORMS) == "Mario Kart 8 Deluxe"
    assert clean_title("Spider-Man (PS4)", PLATFORMS) == "Spider-Man"
    assert clean_title("The Legend of Zelda: Breath of the Wild", PLATFORMS) == "The Legend of Zelda: Breath of the Wild"
    assert guess_platform("Pokemon Legends Z-A - Nintendo Switch 2", PLATFORMS) == "Nintendo Switch 2"
    assert guess_platform("Halo Infinite - Xbox Series X", PLATFORMS) == "Xbox Series X|S"
    assert guess_platform("Among Us", PLATFORMS) is None


def test_barcode_lookup(tmp_path):
    client = make_client(tmp_path)
    platforms = {p["name"]: p["id"] for p in client.get("/api/platforms").json()}
    res = client.get("/api/barcode/045496590420").json()
    assert res["product"] == "Super Mario Odyssey - Nintendo Switch"
    assert res["title"] == "Super Mario Odyssey" and res["platform_id"] == platforms["Nintendo Switch"]
    assert res["owned"] == [] and res["error"] is None

    client.post("/api/games", json={"title": "Spider-Man", "platform_id": platforms["PlayStation 4"], "format": "physical", "barcode": "711719541028"}).raise_for_status()
    res = client.get("/api/barcode/711719541028").json()
    assert [(g["title"], g["platform"]) for g in res["owned"]] == [("Spider-Man", "PlayStation 4")]
    # Same code read as EAN-13
    assert len(client.get("/api/barcode/0711719541028").json()["owned"]) == 1
    assert res["platform_id"] == platforms["PlayStation 4"]


def test_barcode_unknown_error_and_invalid(tmp_path):
    client = make_client(tmp_path)
    res = client.get("/api/barcode/12345678").json()
    assert res["product"] is None and res["error"] is None
    res = client.get("/api/barcode/99999999").json()
    assert res["error"] == "HTTP 429" and res["product"] is None
    assert client.get("/api/barcode/abc").status_code == 422
    assert client.get("/api/barcode/1234").status_code == 422
