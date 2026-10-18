from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: Path = Path("/data")
    # Empty -> SQLite file in data_dir. Example Postgres:
    # postgresql+psycopg://user:pass@host:5432/games
    database_url: str = ""

    # Seconds between games during a bulk cover lookup
    scrape_delay: float = 0.5

    # Build info, set by the Docker image (shown in "Acerca de")
    app_version: str = ""  # set by the image (X.Y.<CI run>); falls back to __version__
    git_sha: str = ""
    git_ref: str = ""
    build_date: str = ""

    # Metadata / cover providers. Each one is enabled when its credentials are set.
    igdb_client_id: str = ""
    igdb_client_secret: str = ""
    steamgriddb_api_key: str = ""
    steam_api_key: str = ""
    steam_id: str = ""
    screenscraper_dev_id: str = ""
    screenscraper_dev_password: str = ""
    screenscraper_user: str = ""
    screenscraper_password: str = ""

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
