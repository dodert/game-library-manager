# Game Library Manager

Self-hosted app to catalogue your video game collection — physical and digital, every console and PC — with cover art fetched from public sources. Inspired by CLZ Games.

## Status

Work in progress. Roadmap:

1. ✅ Core app: FastAPI backend, web UI, SQLite by default (PostgreSQL optional).
2. ✅ Covers & metadata: IGDB, SteamGridDB, Steam, ScreenScraper.
3. ✅ Docker image (amd64/arm64) on GHCR, docker-compose and Unraid template.
4. ✅ CLZ-style extras: CSV import, stats, wishlist, loans.

## Import / export

- **Exportar CSV** downloads the whole library (`/api/export/csv`).
- **Importar CSV** accepts that file back, or a CSV from another collection manager (for example a CLZ Games export). Comma, semicolon or tab separated; UTF-8 or Windows-1252. Headers are matched by name in English or Spanish (`Title`/`Título`, `Platform`/`Plataforma`, `Barcode`/`Código de barras`, `Purchase Price`/`Precio`, …); unknown platforms are created and unrecognised columns are listed after the import. Rows already in the library (same title, platform and format) are skipped. HTML in imported text (CLZ descriptions often carry `<p>`, `<br>`, `&amp;`…) is converted to plain text. A CLZ Games export maps all its collector columns (publisher, developer, genre, series, hardware type, completeness, box, manual, condition, rating, tags, location, storage, loans…); rows with no platform, such as hardware and accessories, go under *Sin plataforma*.

## Docker

Image: `ghcr.io/dodert/game-library-manager` (linux/amd64 and linux/arm64), built by GitHub Actions on every push to `main` and on `v*` git tags. A push to `main` is tagged `latest`, the app version from `app/__init__.py` (e.g. `0.4.1` and `0.4`) and `sha-<commit>`. Pin a version tag in Unraid if you don't want to follow `latest`; bump `__version__` for each release so the version tag isn't reused.

To try a branch before merging it: **Actions → CI → Run workflow**, pick the branch. The image is pushed as `ghcr.io/dodert/game-library-manager:<branch>` (`/` becomes `-`, e.g. `feat-clz-extras`); set that tag as the container's Repository in Unraid. **Actions → Sync Unraid template → Run workflow** does the same for the template, publishing that branch's XML.

```bash
docker run -d --name game-library-manager -p 8000:8000 \
  -v /path/to/data:/data -e PUID=1000 -e PGID=1000 \
  ghcr.io/dodert/game-library-manager:latest
```

Or use [`docker-compose.yml`](docker-compose.yml). Everything lives in `/data` (SQLite database and covers). The container runs as `PUID`:`PGID` (default `99:100`, Unraid's `nobody:users`). The database schema is migrated automatically on start.

## Unraid

The `Sync Unraid template` workflow publishes the template to the public repo [dodert/unraid-templates](https://github.com/dodert/unraid-templates). (Unraid removed the "Template repositories" setting in 6.10, so the template is installed with one command.)

1. In the Unraid terminal:
   ```bash
   mkdir -p /boot/config/plugins/dockerMan/templates-user && curl -fsSL https://raw.githubusercontent.com/dodert/unraid-templates/main/game-library-manager.xml -o /boot/config/plugins/dockerMan/templates-user/my-game-library-manager.xml
   ```
   Run it again to update the template.
2. In **Docker → Add Container**, pick `game-library-manager` from the template list.
3. Fill in the provider keys you have and click **Apply**. Data goes to `/mnt/user/appdata/game-library-manager`.

To list it in **Apps → Private** (Community Applications) instead, download it to CA's private folder:

```bash
mkdir -p /boot/config/plugins/community.applications/private/dodert && curl -fsSL https://raw.githubusercontent.com/dodert/unraid-templates/main/game-library-manager.xml -o /boot/config/plugins/community.applications/private/dodert/game-library-manager.xml
```

## Covers for imported games

**Buscar carátulas** looks every game up in the enabled providers (IGDB, ScreenScraper, SteamGridDB and Steam, best match by title and platform) and downloads the cover. It fills the description and year only where they are empty. Choose **Solo los que nunca se han buscado** to cover games added since the last run (for example after a CSV import), or **Todos** to search the whole library again and replace existing covers. It runs in the background with a progress bar; games with no match are marked "Sin resultados" in their card's dialog. `SCRAPE_DELAY` (seconds between games, default `0.5`) keeps it inside the providers' rate limits.

**Borrar todo** empties the library (games, covers and the platforms added by you or an import) after you type `BORRAR`. Export a CSV first if you want a copy.

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
