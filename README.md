# Game Library Manager

Self-hosted app to catalogue your video game collection — physical and digital, every console and PC — with cover art fetched from public sources. Inspired by CLZ Games.

## Status

Work in progress. Roadmap:

1. Core app: FastAPI backend, web UI, SQLite by default (PostgreSQL optional).
2. Covers & metadata: IGDB, SteamGridDB, Steam, ScreenScraper.
3. Docker image (amd64/arm64) on GHCR, docker-compose and Unraid template.
4. CLZ-style extras: CSV import, stats, wishlist, loans.

## Run locally

```bash
pip install -r requirements-dev.txt
DATA_DIR=./data uvicorn app.main:create_app --factory --reload
# open http://localhost:8000  ·  API docs at /docs
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `DATA_DIR` | `/data` | Database (SQLite), covers and other data |
| `DATABASE_URL` | *(empty)* | Leave empty for SQLite in `DATA_DIR/library.db`. For PostgreSQL: `postgresql+psycopg://user:pass@host:5432/games` |

## Tests

```bash
pytest
```
