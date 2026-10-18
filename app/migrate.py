from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _config(connection) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.attributes["connection"] = connection
    return config


def upgrade_database(engine: Engine) -> None:
    """Bring the schema to the latest revision.

    Databases created before migrations existed (v0.1/v0.2 used create_all) have tables but no
    alembic_version; they are stamped at the revision their columns match, then upgraded.
    """
    with engine.begin() as connection:
        config = _config(connection)
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        if "games" in tables and "alembic_version" not in tables:
            columns = {c["name"] for c in inspector.get_columns("games")}
            command.stamp(config, "0002" if "steam_appid" in columns else "0001")
        command.upgrade(config, "head")
