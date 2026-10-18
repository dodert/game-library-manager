from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: Path = Path("/data")
    # Empty -> SQLite file in data_dir. Example Postgres:
    # postgresql+psycopg://user:pass@host:5432/games
    database_url: str = ""

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{self.data_dir / 'library.db'}"

    @property
    def covers_dir(self) -> Path:
        path = self.data_dir / "covers"
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
