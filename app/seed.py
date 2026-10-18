from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Platform

DEFAULT_PLATFORMS: list[tuple[str, str]] = [
    ("PC", "PC"),
    ("PlayStation", "Sony"), ("PlayStation 2", "Sony"), ("PlayStation 3", "Sony"),
    ("PlayStation 4", "Sony"), ("PlayStation 5", "Sony"), ("PSP", "Sony"), ("PS Vita", "Sony"),
    ("Xbox", "Microsoft"), ("Xbox 360", "Microsoft"), ("Xbox One", "Microsoft"),
    ("Xbox Series X|S", "Microsoft"),
    ("NES", "Nintendo"), ("SNES", "Nintendo"), ("Nintendo 64", "Nintendo"),
    ("GameCube", "Nintendo"), ("Wii", "Nintendo"), ("Wii U", "Nintendo"),
    ("Nintendo Switch", "Nintendo"), ("Nintendo Switch 2", "Nintendo"),
    ("Game Boy", "Nintendo"), ("Game Boy Color", "Nintendo"), ("Game Boy Advance", "Nintendo"),
    ("Nintendo DS", "Nintendo"), ("Nintendo 3DS", "Nintendo"),
    ("Master System", "Sega"), ("Mega Drive", "Sega"), ("Saturn", "Sega"),
    ("Dreamcast", "Sega"), ("Game Gear", "Sega"),
    ("Neo Geo", "SNK"), ("Atari 2600", "Atari"),
]


def seed_platforms(db: Session) -> None:
    existing = set(db.scalars(select(Platform.name)))
    for name, manufacturer in DEFAULT_PLATFORMS:
        if name not in existing:
            db.add(Platform(name=name, manufacturer=manufacturer))
    db.commit()
