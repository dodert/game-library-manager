from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.csv_io import _parse_price
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(Settings(data_dir=tmp_path)))


def upload(client, text, **form):
    return client.post("/api/import/csv", files={"file": ("games.csv", text.encode("utf-8"), "text/csv")}, data=form)


def test_round_trip_own_export(client, tmp_path):
    pc = next(p["id"] for p in client.get("/api/platforms").json() if p["name"] == "PC")
    client.post("/api/games", json={
        "title": "Hades", "platform_id": pc, "format": "digital", "store": "Steam",
        "purchase_price": 19.99, "purchase_date": "2024-05-01", "completion": "completed",
    })
    client.post("/api/games", json={
        "title": "Ico", "platform_id": pc, "format": "physical", "status": "lent",
        "loaned_to": "Ana", "loaned_at": "2026-10-01",
    })
    csv_text = client.get("/api/export/csv").text
    assert csv_text.splitlines()[0].startswith("title,platform,format,status")

    other = TestClient(create_app(Settings(data_dir=tmp_path / "other")))
    res = upload(other, csv_text).json()
    assert res == {"imported": 2, "skipped": 0, "errors": [], "unmapped_columns": []}
    games = {g["title"]: g for g in other.get("/api/games").json()["items"]}
    assert games["Hades"]["purchase_price"] == 19.99 and games["Hades"]["completion"] == "completed"
    assert games["Ico"]["loaned_to"] == "Ana" and games["Ico"]["loaned_at"] == "2026-10-01"

    # Importing the same file again skips duplicates
    assert upload(other, csv_text).json()["skipped"] == 2


def test_foreign_headers_semicolons_and_new_platform(client):
    text = (
        "Título;Plataforma;Código de barras;Fecha de lanzamiento;Precio;Estado;Columna rara\n"
        "Zelda;Nintendo Switch;045496420055;03/03/2017;59,99 €;Wish list;x\n"
        "Panzer Dragoon;Sega Saturn;;1995;12;;y\n"
        ";PC;;;;;\n"
    )
    res = upload(client, text).json()
    assert res["imported"] == 2 and res["skipped"] == 1
    assert res["unmapped_columns"] == ["Columna rara"]
    games = {g["title"]: g for g in client.get("/api/games").json()["items"]}
    assert games["Zelda"]["status"] == "wishlist"
    assert games["Zelda"]["purchase_price"] == 59.99
    assert games["Zelda"]["release_year"] == 2017
    assert games["Zelda"]["format"] == "physical"
    assert games["Panzer Dragoon"]["platform"]["name"] == "Sega Saturn"  # created on the fly


def test_default_format_and_row_errors(client):
    text = "Name,Platform,Purchase Date\nCeleste,PC,not-a-date\nTetris,Game Boy,1989-06-14\n"
    res = upload(client, text, default_format="digital").json()
    assert res["imported"] == 1
    assert res["errors"] == [{"row": 2, "message": "unrecognised date 'not-a-date'"}]
    tetris = client.get("/api/games").json()["items"][0]
    assert tetris["format"] == "digital"


def test_missing_title_column(client):
    res = upload(client, "foo,bar\n1,2\n").json()
    assert res["imported"] == 0 and res["errors"][0]["message"] == "No title column found"


@pytest.mark.parametrize("raw,expected", [
    ("12", 12.0), ("12,5", 12.5), ("1.234,56", 1234.56), ("1,234.56", 1234.56), ("€ 9.99", 9.99), ("", None),
])
def test_parse_price(raw, expected):
    assert _parse_price(raw) == expected


def test_clz_export_sample(client):
    """Real CLZ Games export header and rows (hardware/accessories with no platform)."""
    text = (Path(__file__).parent / "fixtures" / "clz_sample.csv").read_text(encoding="utf-8")
    res = upload(client, text).json()
    assert res["imported"] == 5 and res["skipped"] == 0 and res["errors"] == []
    assert "Type" in res["unmapped_columns"] and "Format" not in res["unmapped_columns"]
    games = {g["title"]: g for g in client.get("/api/games").json()["items"]}
    stick = games["Arcade Stick 8Bitdo"]
    assert stick["platform"]["name"] == "Sin plataforma"
    assert stick["purchase_price"] == 84.95 and stick["purchase_date"] == "2021-09-16"
    assert stick["store"] == "xtralife.com" and stick["barcode"] == "6922621501350"
    assert stick["status"] == "owned" and stick["completion"] == "unplayed" and stick["format"] == "physical"
    assert games["Game & Watch Super Mario Bros"]["purchase_date"] is None
    assert games["Figura Amiibo Link The Legend of Zelda: Tears of the Kingdom"]["release_year"] == 2023
