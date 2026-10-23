from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from app.db import Base
from app.migrate import upgrade_database


def test_migrations_match_models(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    upgrade_database(engine)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


def test_legacy_v01_database_is_upgraded(tmp_path):
    """A database created by v0.1 (create_all, no alembic_version) keeps its data and gains new columns up to the latest revision."""
    engine = create_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE platforms (id INTEGER PRIMARY KEY, name VARCHAR(100) UNIQUE NOT NULL, manufacturer VARCHAR(100))"))
        conn.execute(text(
            "CREATE TABLE games (id INTEGER PRIMARY KEY, title VARCHAR(300) NOT NULL, platform_id INTEGER NOT NULL REFERENCES platforms(id), "
            "format VARCHAR(8) NOT NULL, status VARCHAR(8) NOT NULL, completion VARCHAR(9) NOT NULL, store VARCHAR(100), "
            "edition VARCHAR(150), region VARCHAR(20), barcode VARCHAR(50), release_year INTEGER, purchase_date DATE, "
            "purchase_price NUMERIC(10, 2), notes TEXT, cover_path VARCHAR(500), "
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL)"
        ))
        conn.execute(text("INSERT INTO platforms (id, name) VALUES (1, 'PC')"))
        conn.execute(text("INSERT INTO games (title, platform_id, format, status, completion) VALUES ('Doom', 1, 'digital', 'owned', 'unplayed')"))

    upgrade_database(engine)

    columns = {c["name"] for c in inspect(engine).get_columns("games")}
    assert {"summary", "steam_appid", "loaned_to", "loaned_at"} <= columns
    with engine.connect() as conn:
        assert conn.execute(text("SELECT title FROM games")).scalar() == "Doom"
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0007"


def test_upgrade_is_idempotent(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    upgrade_database(engine)
    upgrade_database(engine)
