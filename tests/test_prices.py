import time

import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

# PriceCharting products by id; prices in cents as the API returns them
PRODUCTS = {
    6910: {"product-name": "Super Mario Odyssey", "console-name": "Nintendo Switch", "upc": "045496590420",
           "loose-price": 2500, "cib-price": 3000, "new-price": 4500, "box-only-price": 800},
    7000: {"product-name": "Hades", "console-name": "Nintendo Switch", "loose-price": 1999, "cib-price": 2499, "new-price": 0},
    7001: {"product-name": "Hades [PAL]", "console-name": "PAL Nintendo Switch", "loose-price": 1500},
}
calls = []


def pricecharting(request: httpx.Request) -> httpx.Response:
    url = request.url
    assert url.host == "www.pricecharting.com" and url.params["t"] == "tok"
    calls.append(dict(url.params))
    if url.path == "/api/products":
        return httpx.Response(200, json={"status": "success", "products": [
            {"id": str(pid), "product-name": p["product-name"], "console-name": p["console-name"]}
            for pid, p in PRODUCTS.items() if url.params["q"].lower().split()[0] in p["product-name"].lower()
        ]})
    assert url.path == "/api/product"
    if "id" in url.params:
        pid = int(url.params["id"])
    elif "upc" in url.params:
        pid = next((i for i, p in PRODUCTS.items() if p.get("upc") == url.params["upc"]), None)
    else:
        pid = next((i for i, p in PRODUCTS.items() if p["product-name"].lower() in url.params["q"].lower()), None)
    if pid not in PRODUCTS:
        return httpx.Response(404, json={"status": "error", "error-message": "No such product"})
    return httpx.Response(200, json={"status": "success", "id": str(pid), **PRODUCTS[pid]})


def make_client(tmp_path, token="tok"):
    calls.clear()
    http = httpx.AsyncClient(transport=httpx.MockTransport(pricecharting))
    settings = Settings(data_dir=tmp_path, pricecharting_token=token, price_delay=0, price_refresh_days=7)
    return TestClient(create_app(settings, http_client=http))


def add(client, title, **fields):
    switch = next(p["id"] for p in client.get("/api/platforms").json() if p["name"] == "Nintendo Switch")
    data = {"title": title, "platform_id": switch, "format": "physical", **fields}
    return client.post("/api/games", json=data).json()


def test_check_by_barcode_then_by_saved_id(tmp_path):
    client = make_client(tmp_path)
    game = add(client, "Mario Odyssey", barcode="045496590420", completeness="CIB", quantity=2)
    res = client.post(f"/api/games/{game['id']}/price")
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["pricecharting_id"] == 6910 and out["price_condition"] == "cib" and out["market_value"] == 60.0
    assert calls[-1]["upc"] == "045496590420"

    PRODUCTS[6910]["cib-price"] = 3200
    try:
        client.post(f"/api/games/{game['id']}/price")
    finally:
        PRODUCTS[6910]["cib-price"] = 3000
    assert calls[-1]["id"] == "6910"  # the product found first is followed from then on
    history = client.get(f"/api/games/{game['id']}/prices").json()
    assert [h["cib"] for h in history] == [30.0, 32.0]
    assert history[0]["loose"] == 25.0 and history[0]["box_only"] == 8.0 and history[0]["graded"] is None
    listed = client.get("/api/games").json()["items"][0]
    assert listed["market_value"] == 64.0


def test_title_search_condition_and_not_found(tmp_path):
    client = make_client(tmp_path)
    hades = add(client, "Hades", has_box=True, has_manual=False)
    out = client.post(f"/api/games/{hades['id']}/price").json()
    assert calls[-1]["q"] == "Hades Nintendo Switch"
    assert out["price_condition"] == "loose" and out["market_value"] == 19.99

    # New is 0 in PriceCharting: no value rather than a free game
    out = client.patch(f"/api/games/{hades['id']}", json={"completeness": "Nuevo"}).json()
    assert out["price_condition"] == "new" and out["market_value"] is None

    unknown = add(client, "Unknown Game")
    res = client.post(f"/api/games/{unknown['id']}/price")
    assert res.status_code == 502 and "No such product" in res.text
    assert client.get(f"/api/games/{unknown['id']}").json()["price_error"] == "No such product"


def test_pick_product_by_hand(tmp_path):
    client = make_client(tmp_path)
    hades = add(client, "Hades")
    found = client.get("/api/prices/search", params={"q": "Hades"}).json()
    assert {p["id"] for p in found} == {7000, 7001}
    client.patch(f"/api/games/{hades['id']}", json={"pricecharting_id": 7001})
    out = client.post(f"/api/games/{hades['id']}/price").json()
    assert calls[-1]["id"] == "7001" and out["market_value"] == 15.0


def test_bulk_job_stats_and_history(tmp_path):
    client = make_client(tmp_path)
    add(client, "Hades", completeness="CIB")
    add(client, "Mario", barcode="045496590420")
    add(client, "Digital game", format="digital")
    add(client, "Sold one", status="sold")
    add(client, "Wanted", status="wishlist", barcode="045496590420")
    st = client.get("/api/prices").json()
    assert st["enabled"] and st["items"] == 3 and st["due"] == 3

    with client:  # the job runs on the app's event loop
        assert client.post("/api/prices", json={"mode": "due"}).status_code == 202
        for _ in range(100):
            st = client.get("/api/prices").json()
            if not st["running"]:
                break
            time.sleep(0.02)
    assert (st["total"], st["found"], st["not_found"], st["due"]) == (3, 3, 0, 0)

    stats = client.get("/api/stats/prices").json()
    # Only the collection counts (the wishlist item is checked but not owned)
    assert stats["total"] == 49.99 and stats["priced"] == 2 and stats["items"] == 2
    assert stats["by_platform"] == {"Nintendo Switch": 49.99}
    assert [t["title"] for t in stats["top"]] == ["Mario", "Hades"]
    assert len(stats["history"]) == 1 and stats["history"][0]["value"] == 49.99


def test_disabled_without_token(tmp_path):
    client = make_client(tmp_path, token="")
    game = add(client, "Hades")
    assert client.post(f"/api/games/{game['id']}/price").status_code == 400
    assert client.post("/api/prices", json={"mode": "all"}).status_code == 400
    assert client.post("/api/prices/test").json()["status"] == "not_configured"
    assert client.get("/api/games").json()["items"][0]["market_value"] is None


def test_connection_test_and_delete_keeps_db_clean(tmp_path):
    client = make_client(tmp_path)
    assert client.post("/api/prices/test").json()["status"] == "ok"
    game = add(client, "Hades")
    client.post(f"/api/games/{game['id']}/price")
    assert client.delete(f"/api/games/{game['id']}").status_code == 204
    assert client.get("/api/stats/prices").json()["history"] == []
