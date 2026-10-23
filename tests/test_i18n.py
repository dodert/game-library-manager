"""Interface translations: every language has the same texts as English, and every text
the page uses exists."""
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

STATIC = Path(__file__).parent.parent / "app" / "static"
LOCALES = sorted((STATIC / "i18n").glob("*.json"))
EN = json.loads((STATIC / "i18n" / "en.json").read_text(encoding="utf-8"))
# Keys built at run time: t(`format.${g.format}`) and the like
DYNAMIC = {
    "column": ["title", "platform", "release_year", "format", "status", "completion", "store",
               "purchase_date", "purchase_price", "market_value", "rating", "item_type"],
    "prices.condition": ["loose", "cib", "new", "box_only", "manual_only", "graded"],
    "format": ["physical", "digital"],
    "status": ["owned", "wishlist", "lent", "sold"],
    "completion": ["unplayed", "playing", "completed", "abandoned"],
    "kind": ["games", "hardware"],
    "scrape": ["cancelled", "finished"],
}


def test_languages_endpoint(tmp_path):
    client = TestClient(create_app(Settings(data_dir=tmp_path, database_url="")))
    languages = client.get("/api/languages").json()
    assert {"code": "en", "name": "English"} in languages
    assert {"code": "es", "name": "Español"} in languages


@pytest.mark.parametrize("path", LOCALES, ids=lambda p: p.stem)
def test_locale_has_every_english_key(path):
    strings = json.loads(path.read_text(encoding="utf-8"))
    assert set(strings) == set(EN), path.name
    for key, text in strings.items():
        # Placeholders such as {n} must survive translation
        assert set(re.findall(r"\{(\w+)\}", text)) == set(re.findall(r"\{(\w+)\}", EN[key])), key


def test_every_key_used_by_the_page_exists():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    used = set(re.findall(r'data-i18n(?:-[a-z-]+)?="([^"]+)"', html))
    used |= set(re.findall(r'(?<![\w.])t\("([a-z_.]+)"', js))
    used |= {f"{group}.{key}" for group, keys in DYNAMIC.items() for key in keys}
    assert used - set(EN) == set()
