import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class GameFormat(str, enum.Enum):
    physical = "physical"
    digital = "digital"


class GameStatus(str, enum.Enum):
    owned = "owned"
    wishlist = "wishlist"
    sold = "sold"
    lent = "lent"


class CompletionStatus(str, enum.Enum):
    unplayed = "unplayed"
    playing = "playing"
    completed = "completed"
    abandoned = "abandoned"


class Platform(Base):
    __tablename__ = "platforms"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    manufacturer: Mapped[str | None] = mapped_column(String(100))

    games: Mapped[list["Game"]] = relationship(back_populates="platform")


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300), index=True)
    platform_id: Mapped[int] = mapped_column(ForeignKey("platforms.id"))
    format: Mapped[GameFormat] = mapped_column(Enum(GameFormat, native_enum=False))
    status: Mapped[GameStatus] = mapped_column(Enum(GameStatus, native_enum=False), default=GameStatus.owned)
    completion: Mapped[CompletionStatus] = mapped_column(
        Enum(CompletionStatus, native_enum=False), default=CompletionStatus.unplayed
    )
    # Digital store / launcher (Steam, PSN, eShop, GOG...) or physical edition
    store: Mapped[str | None] = mapped_column(String(100))
    edition: Mapped[str | None] = mapped_column(String(150))
    region: Mapped[str | None] = mapped_column(String(20))
    barcode: Mapped[str | None] = mapped_column(String(50), index=True)
    release_year: Mapped[int | None]
    purchase_date: Mapped[date | None] = mapped_column(Date)
    purchase_price: Mapped[float | None] = mapped_column(Numeric(10, 2, asdecimal=False))
    notes: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    steam_appid: Mapped[int | None] = mapped_column(index=True)
    cover_path: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    platform: Mapped[Platform] = relationship(back_populates="games")
