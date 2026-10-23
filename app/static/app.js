const $ = (sel) => document.querySelector(sel);
const SKIP_FIELDS = new Set(["cover", "id"]);

const api = async (path, opts = {}) => {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.status === 204 ? null : res.json();
};

let providers = [];
let tab = "collection";
const TAB_STATUS = { collection: ["owned", "lent"], wishlist: ["wishlist"], lent: ["lent"], sold: ["sold"] };
let pendingCover = null; // {provider, urls, thumb} chosen from an online search

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

async function loadPlatforms() {
  const platforms = await api("/api/platforms");
  const options = platforms.map((p) => `<option value="${p.id}">${esc(p.name)}</option>`).join("");
  $("#f-platform").insertAdjacentHTML("beforeend", options);
  $("#game-form [name=platform_id]").innerHTML = options;
}

// Hardware types in use, for the filter and the dialog suggestions
async function loadItemTypes() {
  const types = await api("/api/item-types");
  const select = $("#f-item-type");
  const current = select.value;
  select.length = 1;
  select.insertAdjacentHTML("beforeend", types.map((t) => `<option value="${esc(t.name)}">${esc(t.name)} (${t.count})</option>`).join(""));
  select.value = [...select.options].some((o) => o.value === current) ? current : "";
  const known = new Set([...$("#item-types").options].map((o) => o.value.toLowerCase()));
  $("#item-types").insertAdjacentHTML("beforeend", types.filter((t) => !known.has(t.name.toLowerCase()))
    .map((t) => `<option value="${esc(t.name)}">`).join(""));
}

async function loadProviders() {
  providers = await api("/api/providers");
  $("#steam-import-btn").hidden = !providers.some((p) => p.can_import);
}

const proxied = (provider, url) =>
  url ? `/api/metadata/image?provider=${encodeURIComponent(provider)}&url=${encodeURIComponent(url)}` : null;

// Sources and "cover / data" choices, shared by the bulk lookup and the game dialog.
// Unticked sources are remembered (not ticked ones), so a newly configured source starts ticked.
function loadSourcePrefs() {
  try { return JSON.parse(localStorage.getItem("glm-scrape-prefs") || "{}"); } catch { return {}; }
}

function saveSourcePrefs(selected, covers, details) {
  const excluded = providers.filter((p) => p.enabled && !selected.includes(p.name)).map((p) => p.name);
  try { localStorage.setItem("glm-scrape-prefs", JSON.stringify({ excluded, covers, details })); } catch {}
}

const providerChecks = (name, prefs) => providers.filter((p) => p.enabled).map((p) =>
  `<label class="radio"><input type="checkbox" name="${name}" value="${esc(p.name)}"${(prefs.excluded ?? []).includes(p.name) ? "" : " checked"}> ${esc(p.label)}</label>`,
).join("");

function renderLookupOpts() {
  const prefs = loadSourcePrefs();
  $("#lookup-providers").innerHTML = providerChecks("lookup-provider", prefs);
  $("#use-cover").checked = prefs.covers ?? true;
  $("#use-details").checked = prefs.details ?? true;
}

const lookupProviders = () => [...document.querySelectorAll("#lookup-providers input:checked")].map((el) => el.value);

function providerQuery() {
  const selected = lookupProviders();
  if (!selected.length) throw new Error(t("error.pick_source"));
  return selected.map((name) => `&provider=${encodeURIComponent(name)}`).join("");
}

$("#lookup-opts").addEventListener("change", () =>
  saveSourcePrefs(lookupProviders(), $("#use-cover").checked, $("#use-details").checked));

// What the online searches look for: the "Search as" text when filled, else the title
function searchText() {
  const f = $("#game-form").elements;
  return f.search_title.value.trim() || f.title.value.trim();
}

async function lookup() {
  const title = searchText();
  if (!title) return;
  $("#lookup").hidden = false;
  $("#lookup-results").innerHTML = "";
  $("#lookup-status").textContent = t("lookup.searching");
  try {
    const { results, errors } = await api(`/api/metadata/search?q=${encodeURIComponent(title)}${providerQuery()}`);
    const label = (name) => providers.find((p) => p.name === name)?.label ?? name;
    const failed = Object.entries(errors).map(([name, msg]) => `${label(name)}: ${msg}`);
    const active = lookupProviders().map(label).join(", ");
    $("#lookup-status").textContent =
      t("lookup.results", { n: results.length, sources: active }) + (failed.length ? ` · ${t("lookup.failed", { errors: failed.join(" · ") })}` : "");
    $("#lookup-results").innerHTML = results.map((r, i) => {
      const thumb = proxied(r.provider, r.thumb_url || r.cover_urls[0]);
      return `<div class="result" data-i="${i}">
        ${thumb ? `<img src="${esc(thumb)}" alt="" loading="lazy">` : `<div class="noimg"></div>`}
        <div>
          <div class="r-title">${esc(r.title)}${r.release_year ? ` (${r.release_year})` : ""}</div>
          <div class="r-meta">${esc(label(r.provider))}${r.platforms.length ? " · " + esc(r.platforms.join(", ")) : ""}${r.cover_urls.length ? "" : ` · ${t("lookup.no_cover")}`}</div>
        </div>
      </div>`;
    }).join("");
    $("#lookup-results").onclick = (ev) => {
      const el = ev.target.closest(".result");
      if (el) applyResult(results[Number(el.dataset.i)]);
    };
  } catch (err) {
    $("#lookup-status").textContent = err.message;
  }
}

function applyResult(r) {
  const f = $("#game-form").elements;
  if ($("#use-details").checked) {
    // With a "Search as" text the title is deliberately different (an edition, a pack…): keep it
    if (!f.search_title.value.trim()) f.title.value = r.title;
    for (const key of ["release_year", "summary", "publisher", "developer", "genre", "series"]) if (r[key]) f[key].value = r[key];
  }
  if (r.provider === "steam") f.steam_appid.value = r.external_id;
  if ($("#use-cover").checked && r.cover_urls.length) {
    pendingCover = { provider: r.provider, urls: r.cover_urls };
    showCover(proxied(r.provider, r.thumb_url || r.cover_urls[0]), proxied(r.provider, r.cover_urls[0]));
    $("#cover-preview span").textContent = t("cover.download_on_save");
  }
  $("#lookup").hidden = true;
}

function showCover(src, full = src) {
  $("#cover-preview").hidden = false;
  $("#cover-preview img").src = src;
  $("#cover-preview a").href = full;
}

async function searchCovers() {
  const form = $("#game-form");
  const title = searchText();
  if (!title) return alert(t("error.title_first"));
  const platform = form.elements.platform_id.selectedOptions[0]?.textContent ?? "";
  $("#cover-picker").hidden = false;
  $("#cover-picker-grid").innerHTML = "";
  $("#cover-picker-status").textContent = t("cover.searching");
  try {
    const { options, errors } = await api(`/api/covers/search?q=${encodeURIComponent(title)}&platform=${encodeURIComponent(platform)}${providerQuery()}`);
    const label = (name) => providers.find((p) => p.name === name)?.label ?? name;
    const failed = Object.entries(errors).map(([name, msg]) => `${label(name)}: ${msg}`);
    const matching = options.filter((o) => o.matches).length;
    $("#cover-picker-status").textContent =
      (options.length ? t("cover.found", { n: options.length, matching }) : t("cover.none")) +
      (failed.length ? ` · ${t("lookup.failed", { errors: failed.join(" · ") })}` : "");
    const tile = (o, i) => `<button type="button" class="cover-opt" data-i="${i}" aria-pressed="false" title="${esc(o.title)}${o.release_year ? ` (${o.release_year})` : ""} · ${esc(label(o.provider))}">
        <img src="${esc(proxied(o.provider, o.thumb_url))}" alt="" loading="lazy">
        <span>${esc(label(o.provider))} · ${esc(o.title)}</span>
      </button>`;
    const first = options.findIndex((o) => !o.matches);
    $("#cover-picker-grid").innerHTML = options.map((o, i) =>
      (i === first && matching ? `<h4>${esc(t("cover.other_results"))}</h4>` : "") + tile(o, i)).join("");
    $("#cover-picker-grid").onclick = (ev) => {
      const el = ev.target.closest(".cover-opt");
      if (!el) return;
      const o = options[Number(el.dataset.i)];
      document.querySelectorAll(".cover-opt").forEach((b) => b.setAttribute("aria-pressed", String(b === el)));
      form.elements.cover.value = "";
      pendingCover = { provider: o.provider, urls: o.urls };
      showCover(proxied(o.provider, o.thumb_url), proxied(o.provider, o.urls[0]));
      $("#cover-preview span").textContent = t("cover.from_provider", { provider: label(o.provider) });
    };
  } catch (err) {
    $("#cover-picker-status").textContent = err.message;
  }
}

const money = (n) => n.toLocaleString(i18n.lang, { style: "currency", currency: "EUR" });

// prefix: translation group for the keys (format, completion...); none = show keys as they are
function bars(title, data, prefix = null) {
  const name = (k) => (prefix ? t(`${prefix}.${k}`) : k);
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  if (!entries.length) return "";
  const max = Math.max(...entries.map(([, n]) => n));
  return `<section class="panel"><h3>${esc(title)}</h3>${entries.map(([k, n]) => `
    <div class="bar-row" title="${esc(name(k))}: ${n}">
      <span class="bar-label">${esc(name(k))}</span>
      <span class="bar-track"><span class="bar" style="width:${(n / max) * 100}%"></span></span>
      <span class="bar-value">${n}</span>
    </div>`).join("")}</section>`;
}

async function loadStats() {
  const s = await api("/api/stats");
  $("#stats").textContent =
    t("stats.summary", {
      collection: s.collection, games: s.by_kind.game, hardware: s.by_kind.hardware,
      physical: s.by_format.physical ?? 0, digital: s.by_format.digital ?? 0,
    });
  if (tab !== "stats") return;
  $("#stats-view").innerHTML = `
    <div class="tiles">
      <div class="tile"><div class="tile-value">${s.collection}</div><div class="tile-label">${esc(t("stats.in_collection"))}</div></div>
      <div class="tile"><div class="tile-value">${s.by_status.wishlist ?? 0}</div><div class="tile-label">${esc(t("stats.in_wishlist"))}</div></div>
      <div class="tile"><div class="tile-value">${s.loaned}</div><div class="tile-label">${esc(t("stats.lent"))}</div></div>
      <div class="tile"><div class="tile-value">${money(s.total_spent)}</div><div class="tile-label">${esc(t("stats.spent"))}</div></div>
    </div>
    <div class="panels">
      ${bars(t("stats.by_kind"), { games: s.by_kind.game, hardware: s.by_kind.hardware }, "kind")}
      ${Object.keys(s.by_item_type).length ? bars(t("stats.by_item_type"), s.by_item_type) : ""}
      ${bars(t("stats.by_platform"), s.by_platform)}
      ${bars(t("stats.by_format"), s.by_format, "format")}
      ${bars(t("stats.by_completion"), s.by_completion, "completion")}
    </div>
    <p class="hint">${esc(t("stats.hint"))}</p>`;
}

function setTab(name) {
  tab = name;
  document.querySelectorAll(".tabs:not(.dlg-tabs) [role=tab]").forEach((b) => b.setAttribute("aria-selected", b.dataset.tab === name));
  const isStats = name === "stats";
  $("#filters").hidden = isStats;
  $("#grid").hidden = isStats;
  $("#pager").hidden = isStats;
  $("#stats-view").hidden = !isStats;
  if (isStats) {
    $("#empty").hidden = true;
    $("#letters").hidden = true;
    document.body.classList.remove("has-letters");
    loadStats();
  } else loadGames();
}

const PAGE_SIZE = 60;
const list = { loaded: 0, total: 0, gen: 0, loading: false };

const VIEWS = ["grid", "list", "table"];
let view = "grid";
try { if (VIEWS.includes(localStorage.getItem("glm-view"))) view = localStorage.getItem("glm-view"); } catch {}

const badges = (g) =>
  `<span class="badge">${t(`format.${g.format}`)}</span>${g.item_type ? `<span class="badge">${esc(g.item_type)}</span>` : ""}${g.status !== "owned" ? `<span class="badge">${t(`status.${g.status}`)}</span>` : ""}`;

const cardHtml = (g) => `
    <article class="card" data-id="${g.id}">
      <div class="cover">${g.cover_url ? `<img src="${esc(g.cover_url)}" alt="" loading="lazy">` : "🎮"}</div>
      <div class="info">
        <div class="title">${esc(g.title)}</div>
        <div class="meta">${esc(g.platform.name)}${g.release_year ? " · " + g.release_year : ""}</div>
        <span>${badges(g)}</span>
        ${g.loaned_to ? `<div class="meta">→ ${esc(g.loaned_to)}${g.loaned_at ? " · " + esc(g.loaned_at) : ""}</div>` : ""}
      </div>
    </article>`;

// Sort keys of the API, one per column; the header is the text "column.<key>"
const COLUMNS = [
  "title", "platform", "release_year", "format", "status", "completion", "store", "purchase_date",
  "purchase_price", "rating", "item_type",
];

function tableHead() {
  const sort = $("#sort").value;
  const th = (key) => {
    const label = esc(t(`column.${key}`));
    const dir = sort === key ? "asc" : sort === `-${key}` ? "desc" : null;
    return `<th data-sort="${key}"${dir ? ` aria-sort="${dir === "asc" ? "ascending" : "descending"}"` : ""} title="${esc(t("column.sort_by", { column: t(`column.${key}`) }))}">${label}${dir ? (dir === "asc" ? " ▲" : " ▼") : ""}</th>`;
  };
  return `<table class="games"><thead><tr><th></th>${COLUMNS.map(th).join("")}</tr></thead><tbody></tbody></table>`;
}

// Sort by a column: same column again flips the direction. Columns that are not in the
// sort menu get a temporary option, so the menu always shows the current order.
function sortBy(key) {
  const select = $("#sort");
  const value = select.value === key ? `-${key}` : key;
  let option = [...select.options].find((o) => o.value === value);
  if (!option) {
    option = $("#sort-column") ?? select.appendChild(Object.assign(document.createElement("option"), { id: "sort-column" }));
    option.value = value;
    option.textContent = `${t(`column.${key}`)} ${value.startsWith("-") ? "▼" : "▲"}`;
  }
  select.value = value;
  loadGames();
}

const rowHtml = (g) => `
    <tr data-id="${g.id}">
      <td class="c">${g.cover_url ? `<img src="${esc(g.cover_url)}" alt="" loading="lazy">` : "<span>🎮</span>"}</td>
      <td class="t">${esc(g.title)}</td>
      <td>${esc(g.platform.name)}</td>
      <td class="num">${g.release_year ?? ""}</td>
      <td>${t(`format.${g.format}`)}</td>
      <td>${t(`status.${g.status}`)}${g.loaned_to ? ` → ${esc(g.loaned_to)}` : ""}</td>
      <td>${t(`completion.${g.completion}`)}</td>
      <td>${esc(g.store)}</td>
      <td class="num">${esc(g.purchase_date)}</td>
      <td class="num">${g.purchase_price != null ? money(g.purchase_price) : ""}</td>
      <td class="num">${g.rating != null ? `${g.rating}/10` : ""}</td>
      <td>${g.item_type ? esc(g.item_type) : t("kind.game")}</td>
    </tr>`;

// Where the next page of games is appended, and how each game is drawn, for the current view
const listTarget = () => (view === "table" ? $("#grid tbody") : $("#grid"));
const itemHtml = (g) => (view === "table" ? rowHtml(g) : cardHtml(g));

function resetGrid() {
  $("#grid").className = `grid ${view === "grid" ? "" : view}`.trim();
  $("#grid").innerHTML = view === "table" ? tableHead() : "";
}

function setView(name) {
  view = name;
  try { localStorage.setItem("glm-view", name); } catch {}
  document.querySelectorAll(".views [data-view]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.view === name)));
  loadGames(true);
}

function listParams() {
  const params = new URLSearchParams();
  for (const [key, el] of [["q", "#q"], ["platform_id", "#f-platform"], ["format", "#f-format"], ["sort", "#sort"]]) {
    if ($(el).value) params.set(key, $(el).value);
  }
  const kind = $("#f-kind").value;
  if (kind) params.set("kind", kind);
  if (kind === "hardware" && $("#f-item-type").value) params.set("item_type", $("#f-item-type").value);
  for (const status of TAB_STATUS[tab] ?? []) params.append("status", status);
  return params;
}

function renderPager() {
  const pages = Math.max(1, Math.ceil(list.total / PAGE_SIZE));
  const page = Math.min(pages, Math.max(1, Math.ceil(list.loaded / PAGE_SIZE)));
  const more = list.loaded < list.total;
  $("#pager").hidden = list.total === 0 || tab === "stats";
  $("#pager-info").textContent = t("list.pager", { loaded: list.loaded, total: list.total, page, pages });
  $("#more-btn").hidden = !more;
  $("#more-btn").disabled = list.loading;
  $("#more-btn").textContent = list.loading ? t("list.loading") : t("list.more");
}

// Fetches the next page and appends it. A filter change bumps list.gen, so a page that
// arrives for an old filter is dropped instead of being mixed into the new list.
async function loadMore(size = PAGE_SIZE) {
  if (list.loading || (list.loaded && list.loaded >= list.total)) return;
  const gen = list.gen;
  list.loading = true;
  renderPager();
  try {
    const params = listParams();
    params.set("limit", size);
    params.set("offset", list.loaded);
    const page = await api(`/api/games?${params}`);
    if (gen !== list.gen) return;
    listTarget().insertAdjacentHTML("beforeend", page.items.map(itemHtml).join(""));
    list.loaded += page.items.length;
    list.total = page.total;
    $("#empty").hidden = page.total > 0;
  } finally {
    if (gen === list.gen) list.loading = false;
    renderPager();
  }
  // Keep filling while the sentinel is still on screen (tall windows, small pages)
  if (gen === list.gen && list.loaded < list.total && sentinelVisible()) loadMore();
}

const sentinelVisible = () => $("#pager").getBoundingClientRect().top < window.innerHeight + 400;

// keep: reload as many games as were already shown (after an edit), instead of going back to page 1
async function loadGames(keep = false) {
  const target = keep ? list.loaded : 0;
  list.gen += 1;
  list.loaded = 0;
  list.total = 0;
  list.loading = false;
  resetGrid();
  loadLetters();
  await loadMore();
  while (list.loaded < Math.min(target, list.total) && !list.loading) {
    const before = list.loaded;
    await loadMore();
    if (list.loaded === before) break;
  }
}

// A-Z bar: where the first title of each letter is in the current list (title order only)
const LETTERS = ["#", ..."ABCDEFGHIJKLMNOPQRSTUVWXYZ"];
let letterPositions = {};

async function loadLetters() {
  const sort = $("#sort").value;
  const show = tab !== "stats" && (sort === "title" || sort === "-title");
  const gen = list.gen;
  letterPositions = {};
  if (show) {
    const params = listParams();
    try { letterPositions = await api(`/api/games/letters?${params}`); } catch { letterPositions = {}; }
    if (gen !== list.gen) return;
  }
  const nav = $("#letters");
  nav.hidden = !show || !Object.keys(letterPositions).length;
  document.body.classList.toggle("has-letters", !nav.hidden);
  nav.innerHTML = LETTERS.map((l) =>
    `<button type="button" data-letter="${l}"${l in letterPositions ? "" : " disabled"}>${l}</button>`).join("");
}

// Loads pages until the game at that position is in the list, then scrolls to it
async function jumpTo(position) {
  const gen = list.gen;
  while (list.loaded <= position && list.loaded < list.total && gen === list.gen) {
    while (list.loading) await new Promise((resolve) => setTimeout(resolve, 50));
    if (gen !== list.gen) return;
    await loadMore(500);
  }
  if (gen !== list.gen) return;
  listTarget().children[position]?.scrollIntoView({ block: "start" });
}

let currentLetter = null;
function pickLetter(button) {
  const letter = button?.dataset.letter;
  if (!letter || button.disabled || letter === currentLetter) return;
  currentLetter = letter;
  $("#letters").querySelectorAll("button").forEach((b) => b.classList.toggle("current", b === button));
  jumpTo(letterPositions[letter]);
}

// Tap a letter, or slide a finger along the bar
const letterAt = (ev) => document.elementFromPoint(ev.clientX, ev.clientY)?.closest("#letters button");
$("#letters").addEventListener("pointerdown", (ev) => {
  currentLetter = null;
  $("#letters").setPointerCapture(ev.pointerId);
  pickLetter(letterAt(ev));
});
$("#letters").addEventListener("pointermove", (ev) => {
  if ($("#letters").hasPointerCapture(ev.pointerId)) pickLetter(letterAt(ev));
});
$("#letters").addEventListener("pointerup", () => {
  setTimeout(() => $("#letters").querySelectorAll(".current").forEach((b) => b.classList.remove("current")), 600);
});

new IntersectionObserver((entries) => {
  if (entries.some((e) => e.isIntersecting) && tab !== "stats") loadMore();
}, { rootMargin: "400px" }).observe($("#pager"));

const refresh = () => Promise.all([tab === "stats" ? null : loadGames(true), loadStats(), loadItemTypes()]);

function setPane(name) {
  document.querySelectorAll(".dlg-tabs [role=tab]").forEach((b) => b.setAttribute("aria-selected", b.dataset.pane === name));
  document.querySelectorAll("#game-form .pane").forEach((p) => { p.hidden = p.dataset.pane !== name; });
}

// Hardware needs its type; a game has none
function showKind() {
  const hardware = $("#kind").value === "hardware";
  $("#item-type-label").hidden = !hardware;
  $("#game-form").elements.item_type.required = hardware;
}

function openDialog(game) {
  const form = $("#game-form");
  form.reset();
  pendingCover = null;
  renderLookupOpts();
  $("#lookup").hidden = true;
  $("#cover-preview").hidden = !game?.cover_url;
  $("#cover-picker").hidden = true;
  if (game?.cover_url) {
    showCover(game.cover_url);
    $("#cover-preview span").textContent = t("cover.current");
  }
  $("#dlg-title").textContent = game ? t("game.edit") : t("game.add");
  $("#delete-btn").hidden = !game;
  form.elements.id.value = game?.id ?? "";
  if (game) {
    for (const el of form.elements) {
      if (el.name && !SKIP_FIELDS.has(el.name) && game[el.name] != null) el.value = String(game[el.name]);
    }
  }
  $("#kind").value = game?.item_type ? "hardware" : "game";
  showKind();
  setPane("general");
  $("#scrape-info").textContent = game?.scraped_at
    ? t("game.last_lookup", { date: game.scraped_at.slice(0, 16).replace("T", " ") }) + (game.scrape_error ? ` · ${game.scrape_error}` : "")
    : "";
  $("#dlg").showModal();
}

$("#game-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const form = ev.target;
  const data = {};
  for (const el of form.elements) {
    if (!el.name || SKIP_FIELDS.has(el.name)) continue;
    data[el.name] = el.value === "" ? null : el.value;
  }
  for (const el of form.elements) {
    if (data[el.name] == null) continue;
    if (el.dataset.type === "number") data[el.name] = Number(data[el.name]);
    if (el.dataset.type === "bool") data[el.name] = data[el.name] === "true";
  }
  for (const key of ["platform_id", "release_year", "steam_appid"]) if (data[key] != null) data[key] = Number(data[key]);
  if (data.loaned_to && data.status === "owned") data.status = "lent";
  if ($("#kind").value === "game") data.item_type = null;

  const id = form.elements.id.value;
  try {
    const game = await api(id ? `/api/games/${id}` : "/api/games", {
      method: id ? "PATCH" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    const file = form.elements.cover.files[0];
    if (file) {
      const body = new FormData();
      body.append("file", file);
      await api(`/api/games/${game.id}/cover`, { method: "PUT", body });
    } else if (pendingCover) {
      try {
        await api(`/api/games/${game.id}/cover/fetch`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(pendingCover),
        });
      } catch (err) {
        alert(t("error.cover_download", { error: err.message }));
      }
    }
    $("#dlg").close();
    refresh();
  } catch (err) {
    alert(err.message);
  }
});

$("#delete-btn").addEventListener("click", async () => {
  const id = $("#game-form").elements.id.value;
  if (!confirm(t("game.confirm_delete"))) return;
  await api(`/api/games/${id}`, { method: "DELETE" });
  $("#dlg").close();
  refresh();
});

$("#lookup-btn").addEventListener("click", lookup);
$("#covers-btn").addEventListener("click", searchCovers);
$("#game-form").elements.cover.addEventListener("change", (ev) => {
  const file = ev.target.files[0];
  if (!file) return;
  pendingCover = null;
  showCover(URL.createObjectURL(file));
  $("#cover-preview span").textContent = t("cover.upload_on_save");
});
document.querySelectorAll(".tabs:not(.dlg-tabs) [role=tab]").forEach((b) => b.addEventListener("click", () => setTab(b.dataset.tab)));
document.querySelectorAll(".dlg-tabs [role=tab]").forEach((b) => b.addEventListener("click", () => setPane(b.dataset.pane)));
const IMPORT_PREFS = "glm-import-prefs";
$("#csv-import-btn").addEventListener("click", () => {
  const form = $("#import-form");
  form.reset();
  try {
    const prefs = JSON.parse(localStorage.getItem(IMPORT_PREFS) || "{}");
    for (const key of ["delimiter", "default_format"]) if (prefs[key]) form.elements[key].value = prefs[key];
  } catch { /* storage unavailable */ }
  $("#import-dlg").showModal();
});
$("#import-cancel").addEventListener("click", () => $("#import-dlg").close());
$("#import-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const form = ev.target;
  const body = new FormData(form);
  try {
    localStorage.setItem(IMPORT_PREFS, JSON.stringify({
      delimiter: body.get("delimiter"), default_format: body.get("default_format"),
    }));
  } catch { /* storage unavailable */ }
  $("#import-dlg").close();
  try {
    const r = await api("/api/import/csv", { method: "POST", body });
    let msg = t("import.result", { imported: r.imported, skipped: r.skipped });
    if (r.errors.length) msg += `\n\n${t("import.errors")}\n` + r.errors.slice(0, 10).map((e) => t("import.row_error", { row: e.row, error: e.message })).join("\n");
    if (r.unmapped_columns.length) msg += `\n\n${t("import.unmapped", { columns: r.unmapped_columns.join(", ") })}`;
    alert(msg);
    $("#f-platform").length = 1;
    await loadPlatforms();
    refresh();
  } catch (err) {
    alert(err.message);
  }
});
$("#steam-import-btn").addEventListener("click", async () => {
  if (!confirm(t("steam.confirm"))) return;
  try {
    const r = await api("/api/import/steam", { method: "POST" });
    alert(t("steam.result", { imported: r.imported, skipped: r.skipped }));
    refresh();
  } catch (err) {
    alert(err.message);
  }
});
$("#cancel-btn").addEventListener("click", () => $("#dlg").close());
$("#add-btn").addEventListener("click", () => openDialog(null));

// Add by barcode: games already in the library with that code, then the product name from
// UPCitemdb, then the usual online search in the game dialog
let barcodeResult = null;
let barcodeStream = null;
// Live scanning needs the browser's barcode reader (Chrome/Edge) and HTTPS; anywhere else
// (iPhone, or the app opened over plain http) a photo is taken and the server reads the code
const canScan = "BarcodeDetector" in window && !!navigator.mediaDevices?.getUserMedia;

function barcodeStatus(text, { error = false, action = "" } = {}) {
  const status = $("#barcode-status");
  status.hidden = !text;
  status.textContent = text;
  status.classList.toggle("error", error);
  $("#barcode-continue").hidden = !action;
  $("#barcode-continue").textContent = action;
}

function stopScan() {
  barcodeStream?.getTracks().forEach((track) => track.stop());
  barcodeStream = null;
  $("#barcode-camera").hidden = true;
}

function closeBarcode() {
  stopScan();
  $("#barcode-dlg").close();
}

$("#barcode-btn").addEventListener("click", () => {
  $("#barcode-form").reset();
  barcodeResult = null;
  barcodeStatus("");
  $("#barcode-scan").hidden = !canScan;
  $("#barcode-photo").hidden = canScan;
  $("#barcode-dlg").showModal();
});
$("#barcode-cancel").addEventListener("click", closeBarcode);
$("#barcode-dlg").addEventListener("close", stopScan);

$("#barcode-scan").addEventListener("click", async () => {
  if (barcodeStream) return stopScan();
  try {
    const detector = new BarcodeDetector({ formats: ["ean_13", "ean_8", "upc_a", "upc_e"] });
    barcodeStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
    const video = $("#barcode-camera video");
    video.srcObject = barcodeStream;
    $("#barcode-camera").hidden = false;
    await video.play();
    while (barcodeStream) {
      const [code] = await detector.detect(video);
      if (code) {
        stopScan();
        $("#barcode-form").elements.code.value = code.rawValue;
        $("#barcode-form").requestSubmit();
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
  } catch (err) {
    stopScan();
    barcodeStatus(t("barcode.camera_error", { error: err.message }), { error: true });
  }
});

$("#barcode-photo").addEventListener("click", () => $("#barcode-photo-input").click());
$("#barcode-photo-input").addEventListener("change", async (ev) => {
  const file = ev.target.files[0];
  ev.target.value = "";
  if (!file) return;
  barcodeStatus(t("barcode.reading_photo"));
  const body = new FormData();
  body.append("file", file);
  try {
    const { code } = await api("/api/barcode/scan", { method: "POST", body });
    $("#barcode-form").elements.code.value = code;
    $("#barcode-form").requestSubmit();
  } catch {
    barcodeStatus(t("barcode.photo_failed"), { error: true });
  }
});

$("#barcode-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const code = ev.target.elements.code.value.replace(/\D/g, "");
  if (code.length < 8 || code.length > 14) return barcodeStatus(t("barcode.invalid"), { error: true });
  barcodeStatus(t("barcode.searching"));
  try {
    barcodeResult = await api(`/api/barcode/${code}`);
  } catch (err) {
    return barcodeStatus(err.message, { error: true });
  }
  const r = barcodeResult;
  const notes = [];
  if (r.owned.length) notes.push(t("barcode.owned", { games: r.owned.map((g) => `${g.title} (${g.platform})`).join(", ") }));
  if (r.error) notes.push(t("barcode.lookup_error", { error: r.error }));
  else if (!r.product) notes.push(t("barcode.not_found"));
  if (!notes.length) return addFromBarcode();
  barcodeStatus(notes.join(" "), { error: !r.owned.length && !r.product, action: r.owned.length ? t("barcode.add_anyway") : t("barcode.add_manually") });
});

$("#barcode-continue").addEventListener("click", addFromBarcode);

function addFromBarcode() {
  const r = barcodeResult;
  closeBarcode();
  openDialog(null);
  const form = $("#game-form");
  form.elements.barcode.value = r.code;
  form.elements.format.value = "physical";
  if (r.platform_id) form.elements.platform_id.value = r.platform_id;
  if (r.title) {
    form.elements.title.value = r.title;
    lookup();
  } else {
    form.elements.title.focus();
  }
}
$("#grid").addEventListener("click", async (ev) => {
  const th = ev.target.closest("th[data-sort]");
  if (th) return sortBy(th.dataset.sort);
  const card = ev.target.closest("[data-id]");
  if (card) openDialog(await api(`/api/games/${card.dataset.id}`));
});

let debounce;
$("#q").addEventListener("input", () => { clearTimeout(debounce); debounce = setTimeout(() => loadGames(), 250); });
for (const sel of ["#f-platform", "#f-format", "#f-item-type", "#sort"]) $(sel).addEventListener("change", () => loadGames());
$("#f-kind").addEventListener("change", () => {
  $("#f-item-type").hidden = $("#f-kind").value !== "hardware";
  loadGames();
});
$("#kind").addEventListener("change", showKind);
$("#more-btn").addEventListener("click", loadMore);
document.querySelectorAll(".views [data-view]").forEach((b) => {
  b.setAttribute("aria-pressed", String(b.dataset.view === view));
  b.addEventListener("click", () => setView(b.dataset.view));
});

let scrapePoll = null;

function renderScrape(st) {
  const bar = $("#scrape-bar");
  if (!st.running && !st.finished_at) { bar.hidden = true; return; }
  bar.hidden = false;
  const progress = bar.querySelector("progress");
  progress.max = st.total || 1;
  progress.value = st.done;
  const counts = [
    st.want_covers && t("scrape.new_covers", { n: st.covers }),
    st.want_details && t("scrape.new_details", { n: st.details }),
    t("scrape.found", { n: st.found }),
    t("scrape.not_found", { n: st.not_found }),
    st.failed && t("scrape.failed", { n: st.failed }),
  ].filter(Boolean).join(" · ");
  bar.querySelector(".scrape-text").textContent = st.running
    ? `${t("scrape.running", { sources: st.sources.join(", "), done: st.done, total: st.total })}${st.current ? ` · ${st.current}` : ""} · ${counts}`
    : `${t(st.cancelled ? "scrape.cancelled" : "scrape.finished")}: ${st.done}/${st.total} · ${counts}` +
      (st.errors.length ? ` · ${t("scrape.errors", { errors: st.errors.slice(0, 3).join(" | ") })}` : "");
  $("#scrape-cancel").hidden = !st.running;
  $("#scrape-close").hidden = st.running;
}

async function pollScrape() {
  const st = await api("/api/scrape");
  renderScrape(st);
  if (st.running) {
    scrapePoll = setTimeout(pollScrape, 1500);
    if (tab !== "stats") loadGames();
  } else {
    scrapePoll = null;
    refresh();
  }
  return st;
}

async function openScrapeDialog() {
  const st = await api("/api/scrape");
  if (st.running) { renderScrape(st); return; }
  const enabled = providers.filter((p) => p.enabled);
  const saved = loadSourcePrefs();
  $("#scrape-providers").innerHTML = providerChecks("provider", saved) || esc(t("scrape.no_sources"));
  $("#scrape-providers-hint").hidden = enabled.length > 1;
  const form = $("#scrape-form").elements;
  if (saved.covers !== undefined) form.covers.checked = saved.covers;
  if (saved.details !== undefined) form.details.checked = saved.details;
  $("#scrape-missing-label").textContent = t("scrape.missing", { n: st.never_scraped });
  $("#scrape-all-label").textContent = t("scrape.all", { n: st.library_total });
  $("#scrape-dlg").showModal();
}

$("#scrape-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const data = new FormData(ev.target);
  const body = {
    mode: data.get("mode"),
    providers: data.getAll("provider"),
    covers: ev.target.elements.covers.checked,
    details: ev.target.elements.details.checked,
  };
  if (!body.providers.length) return alert(t("error.pick_source"));
  if (!body.covers && !body.details) return alert(t("error.pick_what"));
  saveSourcePrefs(body.providers, body.covers, body.details);
  $("#scrape-dlg").close();
  try {
    renderScrape(await api("/api/scrape", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }));
    if (!scrapePoll) pollScrape();
  } catch (err) {
    alert(err.message);
  }
});
$("#scrape-btn").addEventListener("click", openScrapeDialog);
$("#scrape-dlg-cancel").addEventListener("click", () => $("#scrape-dlg").close());
$("#scrape-cancel").addEventListener("click", async () => renderScrape(await api("/api/scrape/cancel", { method: "POST" })));
$("#scrape-close").addEventListener("click", () => { $("#scrape-bar").hidden = true; });

$("#reset-btn").addEventListener("click", async () => {
  // The word to type is translated; the API always gets BORRAR
  const word = t("reset.word");
  const answer = prompt(t("reset.prompt", { word }));
  if (answer === null) return;
  if (answer.trim().toUpperCase() !== word.toUpperCase()) { alert(t("reset.nothing")); return; }
  try {
    const r = await api("/api/reset", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirm: "BORRAR" }),
    });
    alert(t("reset.done", { games: r.games_deleted, platforms: r.platforms_deleted }));
    $("#f-platform").length = 1;
    await loadPlatforms();
    refresh();
  } catch (err) {
    alert(err.message);
  }
});

async function loadAbout() {
  const a = await api("/api/about");
  const commit = a.commit
    ? ` · <a href="https://github.com/dodert/game-library-manager/commit/${esc(a.commit)}" target="_blank" rel="noopener">${esc(a.commit.slice(0, 7))}</a>`
    : "";
  const built = a.build_date ? ` · ${esc(t("about.built", { date: a.build_date.slice(0, 16).replace("T", " ") }))}` : "";
  const db = a.database === "postgresql" ? "PostgreSQL" : a.database === "sqlite" ? "SQLite" : a.database;
  $("#about").innerHTML =
    `Game Library Manager v${esc(a.version)}${a.ref ? ` (${esc(a.ref)})` : ""}${commit}${built} · ${esc(t("about.database", { db, schema: a.schema }))}`;
}

async function openSettings() {
  const languages = await api("/api/languages");
  $("#lang-select").innerHTML = languages.map((l) => `<option value="${esc(l.code)}">${esc(l.name)}</option>`).join("");
  $("#lang-select").value = i18n.lang;
  renderProviderTests();
  $("#settings-dlg").showModal();
}

function renderProviderTests() {
  $("#provider-tests").innerHTML = providers.map((p) => `
    <li data-provider="${esc(p.name)}">
      <span class="p-name">${esc(p.label)}</span>
      <span class="p-result">${p.enabled ? "" : esc(t("settings.test_not_configured"))}</span>
      <button type="button" class="p-test">${esc(t("settings.test"))}</button>
    </li>`).join("");
}

async function testProvider(li) {
  const result = li.querySelector(".p-result");
  const button = li.querySelector(".p-test");
  button.disabled = true;
  result.className = "p-result";
  result.textContent = t("settings.testing");
  try {
    const r = await api(`/api/providers/${encodeURIComponent(li.dataset.provider)}/test`, { method: "POST" });
    if (r.status === "ok") {
      let text = t("settings.test_ok", { results: r.results, ms: r.ms });
      if (r.library_games !== null) text += " · " + t("settings.test_library", { n: r.library_games });
      result.textContent = text;
    } else if (r.status === "not_configured") {
      result.textContent = t("settings.test_not_configured");
    } else {
      result.textContent = t("settings.test_error", { error: r.error });
    }
    if (r.status !== "not_configured") result.classList.add(r.status);
  } catch (err) {
    result.textContent = t("settings.test_error", { error: err.message });
    result.classList.add("error");
  } finally {
    button.disabled = false;
  }
}

$("#provider-tests").addEventListener("click", (ev) => {
  const button = ev.target.closest(".p-test");
  if (button) testProvider(button.closest("li"));
});
$("#provider-test-all").addEventListener("click", () => {
  $("#provider-tests").querySelectorAll("li").forEach(testProvider);
});

$("#settings-btn").addEventListener("click", openSettings);
$("#settings-cancel").addEventListener("click", () => $("#settings-dlg").close());
$("#settings-form").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const lang = $("#lang-select").value;
  $("#settings-dlg").close();
  if (lang === i18n.lang) return;
  setLang(lang);
  location.reload();
});

initI18n().finally(() => {
  renderPager();
  Promise.all([loadPlatforms(), loadProviders()]).then(refresh);
  loadAbout();
  api("/api/scrape").then((st) => { if (st.running) pollScrape(); });
});
