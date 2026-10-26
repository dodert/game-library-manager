import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def make_client(tmp_path, **auth):
    return TestClient(create_app(Settings(data_dir=tmp_path, **auth)))


def test_no_login_when_not_configured(tmp_path):
    client = make_client(tmp_path)
    assert client.get("/api/games").status_code == 200
    assert client.get("/api/about").json()["auth"] is False
    assert client.get("/login", follow_redirects=False).headers["location"] == "/"


def test_only_one_variable_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="AUTH_USERNAME and AUTH_PASSWORD"):
        make_client(tmp_path, auth_username="admin")


def test_login_required(tmp_path):
    client = make_client(tmp_path, auth_username="admin", auth_password="s3cret")
    assert client.get("/api/games").status_code == 401
    assert client.get("/covers/x.jpg", follow_redirects=False).status_code == 303
    page = client.get("/", follow_redirects=False)
    assert page.status_code == 303 and page.headers["location"] == "/login"
    # The login page, its assets and the Docker health check stay reachable
    assert 'action="/login"' in client.get("/login").text
    assert client.get("/static/style.css").status_code == 200
    assert client.get("/static/i18n/es.json").status_code == 200
    assert client.get("/api/health").status_code == 200


def test_wrong_password_then_login_and_logout(tmp_path):
    client = make_client(tmp_path, auth_username="admin", auth_password="s3cret")
    bad = client.post("/login", data={"username": "admin", "password": "nope"}, follow_redirects=False)
    assert bad.headers["location"] == "/login?error=1" and "glm_session" not in bad.cookies
    ok = client.post("/login", data={"username": "admin", "password": "s3cret"}, follow_redirects=False)
    assert ok.headers["location"] == "/" and "httponly" in ok.headers["set-cookie"].lower()
    assert client.get("/api/games").status_code == 200
    assert client.get("/api/about").json()["auth"] is True
    client.get("/logout")
    assert client.get("/api/games").status_code == 401


def test_session_survives_restart_but_not_password_change(tmp_path):
    first = make_client(tmp_path, auth_username="admin", auth_password="s3cret")
    first.post("/login", data={"username": "admin", "password": "s3cret"})
    cookie = first.cookies["glm_session"]
    same = make_client(tmp_path, auth_username="admin", auth_password="s3cret")
    same.cookies.set("glm_session", cookie)
    assert same.get("/api/games").status_code == 200
    changed = make_client(tmp_path, auth_username="admin", auth_password="other")
    changed.cookies.set("glm_session", cookie)
    assert changed.get("/api/games").status_code == 401
    forged = make_client(tmp_path, auth_username="admin", auth_password="s3cret")
    forged.cookies.set("glm_session", "9999999999.deadbeef")
    assert forged.get("/api/games").status_code == 401


def test_forged_cookie_with_huge_expiry_is_rejected_not_a_crash(tmp_path):
    client = TestClient(create_app(Settings(data_dir=tmp_path, auth_username="admin", auth_password="pw")))
    client.cookies.set("glm_session", "9" * 5000 + ".abc")
    assert client.get("/api/games").status_code == 401
