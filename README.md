# Game Library Manager

[![Support me on Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/dodert)

Self-hosted app to catalogue your video game collection — physical and digital, every console and PC — with cover art fetched from public sources. Inspired by CLZ Games.

> **Note:** this project has been almost entirely vibe-coded with an AI coding assistant ([Claude Code](https://claude.com/claude-code)).

## Status

Work in progress. Roadmap:

1. ✅ Core app: FastAPI backend, web UI, SQLite by default (PostgreSQL optional).
2. ✅ Covers & metadata: IGDB, SteamGridDB, Steam, ScreenScraper.
3. ✅ Docker image (amd64/arm64) on GHCR, docker-compose and Unraid template.
4. ✅ CLZ-style extras: CSV import, stats, wishlist, loans.

## Languages

The interface is in English by default and also in Spanish. Change it in **⚙ Settings → Language**; the choice is saved in that browser.

To add a language, copy `app/static/i18n/en.json` to `app/static/i18n/<code>.json` (for example `fr.json`), set `"_name"` to the language's own name (`"Français"`) and translate the values, keeping placeholders such as `{n}` as they are. It shows up in Settings with no other change; any text left out falls back to English. `tests/test_i18n.py` checks that every language has all the texts and placeholders.

## Import / export

- **Exportar CSV** downloads the whole library (`/api/export/csv`).
- **Importar CSV** accepts that file back, or a CSV from another collection manager (for example a CLZ Games export). Pick the separator in the import dialog (semicolon for CLZ, comma or tab), or let it detect it from the header row; UTF-8 or Windows-1252. Multi-line quoted fields are supported. Headers are matched by name in English or Spanish (`Title`/`Título`, `Platform`/`Plataforma`, `Barcode`/`Código de barras`, `Purchase Price`/`Precio`, …); unknown platforms are created and unrecognised columns are listed after the import. Rows already in the library (same title, platform and format) are skipped. HTML in imported text (CLZ descriptions often carry `<p>`, `<br>`, `&amp;`…) is converted to plain text. A CLZ Games export maps all its collector columns (publisher, developer, genre, series, hardware type, completeness, box, manual, condition, rating, tags, location, storage, loans…); rows with no platform, such as hardware and accessories, go under *Sin plataforma*.
- **Videojuegos y hardware**: an item with a hardware type (CLZ's *Hardware Type*: Console, Amiibo, Funda…) is hardware; anything else is a video game. The filter bar can show only video games or only hardware, and then one hardware type; in the game dialog, *Tipo* switches between *Videojuego* and *Hardware* (which asks for the hardware type). Statistics count both and break hardware down by type.

## Docker

Image: `ghcr.io/dodert/game-library-manager` (linux/amd64 and linux/arm64), built by GitHub Actions on every push to `main` and on `v*` git tags. Versions follow [SemVer](https://semver.org): `main` builds are the release version in `app/__init__.py` (`__version__`, e.g. `0.5.0`), so bump it in every PR (`Z` for fixes, `Y` for features). A push to `main` is tagged `latest`, `X.Y.Z`, `X.Y` and `sha-<commit>`. Pin a version tag in Unraid if you don't want to follow `latest`. The footer shows the version.

To try a branch before merging it: **Actions → CI → Run workflow**, pick the branch. The image is pushed as `ghcr.io/dodert/game-library-manager:<branch>` (`/` becomes `-`, e.g. `feat-clz-extras`), and also as `pre-release` and a SemVer pre-release version `X.Y.Z-<branch>.<run>` (e.g. `0.5.0-feat-bulk-scrape.27`) when the branch is not `main`; pre-releases sort below the release and never take a `main` number; set that tag as the container's Repository in Unraid. **Actions → Sync Unraid template → Run workflow** does the same for the template, publishing that branch's XML.

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

**Buscar carátulas** looks every game up in the providers you tick (any of the enabled ones: IGDB, ScreenScraper, SteamGridDB and Steam; best match by title and platform). Choose what to fetch: the **cover**, the **game data** (description, year, publisher, developer, genre and series), or both. A game's **Buscar como** field (in its dialog, under the title) is searched instead of the title when filled, for editions or packs whose name the providers don't know. Data only fills fields that are empty; IGDB and ScreenScraper provide publisher/developer/genre, IGDB also the series, SteamGridDB only covers. Choose **Solo los que nunca se han buscado** to cover games added since the last run (for example after a CSV import), or **Todos** to search the whole library again and replace existing covers. It runs in the background with a progress bar; games with no match are marked "Sin resultados" in their card's dialog. `SCRAPE_DELAY` (seconds between games, default `0.5`) keeps it inside the providers' rate limits.

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

In the add/edit dialog, **Buscar en internet** searches every enabled provider and lets you pick metadata and a cover; the cover is downloaded and stored in `DATA_DIR/covers`. **Buscar carátulas** (General tab, next to the cover) shows every cover the providers have for the title, closest title matches first, so you can pick one when there is more than one; it is downloaded when you save. **Importar Steam** adds your owned Steam games and downloads their covers in the background.

## Tests

```bash
pytest
```

## Support

If this app is useful to you, you can support its development with a coffee on Ko-fi. Thank you!

[![Support me on Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/dodert)

## License

[GPL-3.0](LICENSE)
