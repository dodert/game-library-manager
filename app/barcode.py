"""Barcode (EAN/UPC) lookup. None of the metadata providers search by barcode, so the product
name comes from UPCitemdb's free plan (no key, 100 lookups a day per IP) and the providers are
then searched by that name."""
import io
import re

import httpx
import zxingcpp
from PIL import Image, ImageOps

MAX_PHOTO_PIXELS = 50_000_000

UPCITEMDB_URL = "https://api.upcitemdb.com/prod/trial/lookup"
BARCODE_PATTERN = r"^\d{8,14}$"

# Short names shops use in product titles -> platform name in the app
PLATFORM_ALIASES = {
    "ps1": "PlayStation", "psx": "PlayStation", "ps2": "PlayStation 2", "ps3": "PlayStation 3",
    "ps4": "PlayStation 4", "ps5": "PlayStation 5", "psvita": "PS Vita", "vita": "PS Vita",
    "switch": "Nintendo Switch", "switch 2": "Nintendo Switch 2", "3ds": "Nintendo 3DS", "nds": "Nintendo DS",
    "xbox series x": "Xbox Series X|S", "xbox series s": "Xbox Series X|S", "gba": "Game Boy Advance",
    "n64": "Nintendo 64", "genesis": "Mega Drive",
}
# Separators shops put between the game and the platform ("Hades - Nintendo Switch", "Hades (PS4)")
_SUFFIX = re.compile(r"(?:\s+[-–—|]\s+|\s*[:,]\s*|\s*\()([^()|:,]+?)\)?\s*$")
# Packaging words that don't help a title search
_NOISE = re.compile(r"\b(video ?game|standard edition|pal|ntsc)\b", re.I)


def read_barcode(photo: bytes) -> str | None:
    """EAN/UPC in a photo, for phones that can't scan live (no HTTPS or no BarcodeDetector)."""
    try:
        image = Image.open(io.BytesIO(photo))
        if image.width * image.height > MAX_PHOTO_PIXELS:
            return None
        image = ImageOps.exif_transpose(image).convert("L")
    except (OSError, ValueError, Image.DecompressionBombError):
        return None
    image.thumbnail((2000, 2000))
    for barcode in zxingcpp.read_barcodes(image, formats=zxingcpp.BarcodeFormat.EANUPC):
        if valid_barcode(barcode.text):
            return barcode.text
    return None


def valid_barcode(code: str) -> bool:
    return bool(re.match(BARCODE_PATTERN, code))


def guess_platform(text: str, platform_names: list[str]) -> str | None:
    """Platform named in a product title: the longest app platform name or alias found in it."""
    lowered = f" {text.lower()} "
    candidates = {name.lower(): name for name in platform_names}
    known = {name.lower() for name in platform_names}
    for alias, name in PLATFORM_ALIASES.items():
        if name.lower() in known:
            candidates.setdefault(alias, candidates[name.lower()])
    found = [key for key in candidates if re.search(rf"(?<![\w]){re.escape(key)}(?![\w])", lowered)]
    return candidates[max(found, key=len)] if found else None


def clean_title(title: str, platform_names: list[str]) -> str:
    """Product title without the platform suffix and packaging words, to search the providers."""
    text = re.sub(r"\s{2,}", " ", _NOISE.sub("", title)).strip()
    while (match := _SUFFIX.search(text)) and guess_platform(match.group(1), platform_names):
        text = text[: match.start()].strip()
    return text.strip(" -–—|:,") or title.strip()


async def lookup_upcitemdb(http: httpx.AsyncClient, code: str) -> dict | None:
    """{"title", "brand"} for a barcode, or None when UPCitemdb doesn't know it."""
    res = await http.get(UPCITEMDB_URL, params={"upc": code})
    if res.status_code in (400, 404):  # invalid or unknown code
        return None
    res.raise_for_status()
    items = res.json().get("items") or []
    if not items or not items[0].get("title"):
        return None
    return {"title": items[0]["title"].strip(), "brand": (items[0].get("brand") or "").strip() or None}
