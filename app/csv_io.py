"""CSV export and import.

Import accepts this app's own export and, on a best-effort basis, CSV exports from other
collection managers (such as CLZ Games): headers are matched case-insensitively against
the aliases below, and anything unrecognised is reported back as an unmapped column.
"""
import csv
import io
import re
import unicodedata
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .models import CompletionStatus, Game, GameFormat, GameStatus, Platform

EXPORT_FIELDS = [
    "title", "platform", "format", "status", "completion", "store", "edition", "region",
    "barcode", "release_year", "purchase_date", "purchase_price", "loaned_to", "loaned_at",
    "notes", "summary", "steam_appid",
]

ALIASES = {
    "title": ["title", "name", "game", "titulo", "nombre", "juego"],
    "platform": ["platform", "plataforma", "system", "sistema", "console", "consola"],
    "format": ["format", "formato", "media", "medium", "type", "tipo"],
    "status": ["status", "estado", "collection status", "owned"],
    "completion": ["completion", "progreso", "progress", "completed", "played", "played status"],
    "store": ["store", "tienda", "launcher", "purchase store", "storefront"],
    "edition": ["edition", "edicion"],
    "region": ["region"],
    "barcode": ["barcode", "upc", "ean", "codigo de barras"],
    "release_year": ["release_year", "release year", "year", "ano", "release date", "fecha de lanzamiento"],
    "purchase_date": ["purchase_date", "purchase date", "fecha compra", "fecha de compra", "date added"],
    "purchase_price": ["purchase_price", "purchase price", "price", "precio", "precio compra"],
    "loaned_to": ["loaned_to", "loaned to", "prestado a", "loan to"],
    "loaned_at": ["loaned_at", "loan date", "fecha prestamo"],
    "notes": ["notes", "notas", "comments", "comentarios"],
    "summary": ["summary", "descripcion", "description", "plot"],
    "steam_appid": ["steam_appid", "steam appid", "steam app id"],
}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", text.strip().lower().replace("_", " "))


ALIAS_LOOKUP = {_norm(alias): field for field, aliases in ALIASES.items() for alias in aliases}


def export_csv(db: Session) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=EXPORT_FIELDS)
    writer.writeheader()
    games = db.scalars(select(Game).options(selectinload(Game.platform)).order_by(Game.title, Game.id))
    for game in games:
        row = {f: getattr(game, f) for f in EXPORT_FIELDS if f != "platform"}
        row["platform"] = game.platform.name
        for key, value in row.items():
            if hasattr(value, "value"):
                row[key] = value.value
            elif value is None:
                row[key] = ""
        writer.writerow(row)
    return out.getvalue()


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def _parse_format(value: str, default: GameFormat) -> GameFormat:
    v = _norm(value)
    if not v:
        return default
    if any(w in v for w in ("digital", "download", "descarga", "steam", "psn", "eshop", "gog", "epic")):
        return GameFormat.digital
    return GameFormat.physical


def _parse_status(value: str) -> GameStatus:
    v = _norm(value)
    if "wish" in v or "deseado" in v:
        return GameStatus.wishlist
    if "sold" in v or "vendido" in v:
        return GameStatus.sold
    if "loan" in v or "lent" in v or "prestado" in v:
        return GameStatus.lent
    return GameStatus.owned


def _parse_completion(value: str) -> CompletionStatus:
    v = _norm(value)
    if v in ("yes", "si", "true", "1") or any(w in v for w in ("complet", "finish", "beat", "terminad")):
        return CompletionStatus.completed
    if "playing" in v or "jugando" in v or "progress" in v:
        return CompletionStatus.playing
    if "abandon" in v or "dropped" in v:
        return CompletionStatus.abandoned
    return CompletionStatus.unplayed


def _parse_date(value: str) -> date | None:
    value = value.strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y", "%b %d, %Y", "%d %b %Y", "%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date '{value}'")


def _parse_year(value: str) -> int | None:
    match = re.search(r"(19|20)\d{2}", value)
    return int(match.group()) if match else None


def _parse_price(value: str) -> float | None:
    value = re.sub(r"[^\d,.\-]", "", value)
    if not value:
        return None
    if "," in value and "." in value:
        # The last separator is the decimal one: 1.234,56 or 1,234.56
        value = value.replace(".", "").replace(",", ".") if value.rfind(",") > value.rfind(".") else value.replace(",", "")
    else:
        value = value.replace(",", ".")
    return float(value)


def import_csv(db: Session, raw: bytes, default_format: GameFormat, skip_duplicates: bool = True) -> dict:
    text = _decode(raw)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    headers = reader.fieldnames or []
    mapping: dict[str, str] = {}
    unmapped = []
    for header in headers:
        field = ALIAS_LOOKUP.get(_norm(header or ""))
        if field and field not in mapping.values():
            mapping[header] = field
        elif header:
            unmapped.append(header)
    if "title" not in mapping.values():
        return {"imported": 0, "skipped": 0, "unmapped_columns": unmapped,
                "errors": [{"row": 1, "message": "No title column found"}]}

    platforms = {p.name.lower(): p for p in db.scalars(select(Platform))}
    existing = set(
        db.execute(select(func.lower(Game.title), Game.platform_id, Game.format)).all()
    ) if skip_duplicates else set()

    imported, skipped, errors = 0, 0, []
    for line, row in enumerate(reader, start=2):
        values = {field: (row.get(header) or "").strip() for header, field in mapping.items()}
        title = values.get("title", "")
        if not title:
            skipped += 1
            continue
        try:
            platform_name = values.get("platform") or "PC"
            platform = platforms.get(platform_name.lower())
            if not platform:
                platform = Platform(name=platform_name[:100])
                db.add(platform)
                db.flush()
                platforms[platform_name.lower()] = platform
            game_format = _parse_format(values.get("format", ""), default_format)
            key = (title.lower(), platform.id, game_format)
            if key in existing:
                skipped += 1
                continue
            year = values.get("release_year", "")
            game = Game(
                title=title[:300],
                platform_id=platform.id,
                format=game_format,
                status=_parse_status(values.get("status", "")),
                completion=_parse_completion(values.get("completion", "")),
                store=values.get("store") or None,
                edition=values.get("edition") or None,
                region=values.get("region") or None,
                barcode=values.get("barcode") or None,
                release_year=_parse_year(year) if year else None,
                purchase_date=_parse_date(values.get("purchase_date", "")),
                purchase_price=_parse_price(values.get("purchase_price", "")),
                loaned_to=values.get("loaned_to") or None,
                loaned_at=_parse_date(values.get("loaned_at", "")),
                notes=values.get("notes") or None,
                summary=values.get("summary") or None,
                steam_appid=int(values["steam_appid"]) if values.get("steam_appid", "").isdigit() else None,
            )
            if game.loaned_to and game.status == GameStatus.owned:
                game.status = GameStatus.lent
            db.add(game)
            existing.add(key)
            imported += 1
        except ValueError as exc:
            errors.append({"row": line, "message": str(exc)})
    db.commit()
    return {"imported": imported, "skipped": skipped, "errors": errors, "unmapped_columns": unmapped}
