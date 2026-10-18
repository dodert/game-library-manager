# Game Library Manager

Self-hosted app to catalogue your video game collection — physical and digital, every console and PC — with cover art fetched from public sources. Inspired by CLZ Games.

## Status

Work in progress. Roadmap:

1. ✅ Core app: FastAPI backend, web UI, SQLite by default (PostgreSQL optional).
2. ✅ Covers & metadata: IGDB, SteamGridDB, Steam, ScreenScraper.
3. ✅ Docker image (amd64/arm64) on GHCR, docker-compose and Unraid template.
4. CLZ-style extras: CSV import, stats, wishlist, loans.

## Docker

Image: `ghcr.io/dodert/game-library-manager` (linux/amd64 and linux/arm64), built by GitHub Actions on every push to `main` (`latest`) and on `v*` tags (`1.2.3`, `1.2`).

```bash
docker run -d --name game-library-manager -p 8000:8000 \
  -v /path/to/data:/data -e PUID=1000 -e PGID=1000 \
  ghcr.io/dodert/game-library-manager:latest
```

Or use [`docker-compose.yml`](docker-compose.yml). Everything lives in `/data` (SQLite database and covers). The container runs as `PUID`:`PGID` (default `99:100`, Unraid's `nobody:users`). The database schema is migrated automatically on start.

## Unraid

**Option A — template repository.** The template is published to the public repo [dodert/unraid-templates](https://github.com/dodert/unraid-templates) by the `Sync Unraid template` workflow. In Unraid, add `https://github.com/dodert/unraid-templates` to **Docker → Template repositories**, save, then pick `game-library-manager` in **Docker → Add Container**.

**Option B — manual.**

1. Copy [`unraid/game-library-manager.xml`](unraid/game-library-manager.xml) to `/boot/config/plugins/dockerMan/templates-user/my-game-library-manager.xml` on the server.
2. In **Docker → Add Container**, pick `game-library-manager` from the template list.
3. Fill in the provider keys you have and click **Apply**. Data goes to `/mnt/user/appdata/game-library-manager`.

## Run locally

```bash
pip install -r requirements-dev.txt
DATA_DIR=./data uvicorn app.main:create_app --factory --reload
# open http://localhost:8000  ·  API docs at /docs
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `PUID` / `PGID` | `99` / `100` | (Docker) user and group the app runs as |
| `TZ` | `Etc/UTC` | (Docker) time zone |
| `PORT` | `8000` | (Docker) port inside the container |
| `DATA_DIR` | `/data` | Database (SQLite), covers and other data |
| `DATABASE_URL` | *(empty)* | Leave empty for SQLite in `DATA_DIR/library.db`. For PostgreSQL: `postgresql+psycopg://user:pass@host:5432/games` |

### Metadata and cover providers

Each provider turns on when its variables are set. Steam store search works without a key.

| Provider | Variables | Where to get them |
|---|---|---|
| IGDB | `IGDB_CLIENT_ID`, `IGDB_CLIENT_SECRET` | Register an application at https://dev.twitch.tv/console (see https://api-docs.igdb.com/#account-creation) |
| SteamGridDB | `STEAMGRIDDB_API_KEY` | https://www.steamgriddb.com/profile/preferences/api |
| Steam (library import) | `STEAM_API_KEY`, `STEAM_ID` | Key: https://steamcommunity.com/dev/apikey · `STEAM_ID` is your 64-bit SteamID; your profile's game details must be public |
| ScreenScraper | `SCREENSCRAPER_DEV_ID`, `SCREENSCRAPER_DEV_PASSWORD`, `SCREENSCRAPER_USER`, `SCREENSCRAPER_PASSWORD` | User account at https://www.screenscraper.fr ; developer credentials are requested on its forum |

In the add/edit dialog, **Buscar en internet** searches every enabled provider and lets you pick metadata and a cover; the cover is downloaded and stored in `DATA_DIR/covers`. **Importar Steam** adds your owned Steam games and downloads their covers in the background.

## Tests

```bash
pytest
```
