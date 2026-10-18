const $ = (sel) => document.querySelector(sel);
const FORMAT = { physical: "Físico", digital: "Digital" };
const SKIP_FIELDS = new Set(["cover", "id"]);
const STATUS = { owned: "En colección", wishlist: "Wishlist", lent: "Prestado", sold: "Vendido" };

const api = async (path, opts = {}) => {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.status === 204 ? null : res.json();
};

let providers = [];
let tab = "collection";
const TAB_STATUS = { collection: ["owned", "lent"], wishlist: ["wishlist"], lent: ["lent"], sold: ["sold"] };
const COMPLETION = { unplayed: "Sin jugar", playing: "Jugando", completed: "Completado", abandoned: "Abandonado" };
let pendingCover = null; // {provider, urls, thumb} chosen from an online search

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

async function loadPlatforms() {
  const platforms = await api("/api/platforms");
  const options = platforms.map((p) => `<option value="${p.id}">${esc(p.name)}</option>`).join("");
  $("#f-platform").insertAdjacentHTML("beforeend", options);
  $("#game-form [name=platform_id]").innerHTML = options;
}

async function loadProviders() {
  providers = await api("/api/providers");
  $("#steam-import-btn").hidden = !providers.some((p) => p.can_import);
}

const proxied = (provider, url) =>
  url ? `/api/metadata/image?provider=${encodeURIComponent(provider)}&url=${encodeURIComponent(url)}` : null;

async function lookup() {
  const title = $("#game-form").elements.title.value.trim();
  if (!title) return;
  $("#lookup").hidden = false;
  $("#lookup-results").innerHTML = "";
  $("#lookup-status").textContent = "Buscando…";
  try {
    const { results, errors } = await api(`/api/metadata/search?q=${encodeURIComponent(title)}`);
    const label = (name) => providers.find((p) => p.name === name)?.label ?? name;
    const failed = Object.entries(errors).map(([name, msg]) => `${label(name)}: ${msg}`);
    const active = providers.filter((p) => p.enabled).map((p) => p.label).join(", ");
    $("#lookup-status").textContent =
      `${results.length} resultados (${active})` + (failed.length ? ` · Error en ${failed.join(" · ")}` : "");
    $("#lookup-results").innerHTML = results.map((r, i) => {
      const thumb = proxied(r.provider, r.thumb_url || r.cover_urls[0]);
      return `<div class="result" data-i="${i}">
        ${thumb ? `<img src="${esc(thumb)}" alt="" loading="lazy">` : `<div class="noimg"></div>`}
        <div>
          <div class="r-title">${esc(r.title)}${r.release_year ? ` (${r.release_year})` : ""}</div>
          <div class="r-meta">${esc(label(r.provider))}${r.platforms.length ? " · " + esc(r.platforms.join(", ")) : ""}${r.cover_urls.length ? "" : " · sin carátula"}</div>
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
  f.title.value = r.title;
  if (r.release_year) f.release_year.value = r.release_year;
  if (r.summary) f.summary.value = r.summary;
  for (const key of ["publisher", "developer", "genre", "series"]) if (r[key]) f[key].value = r[key];
  if (r.provider === "steam") f.steam_appid.value = r.external_id;
  if (r.cover_urls.length) {
    pendingCover = { provider: r.provider, urls: r.cover_urls };
    showCover(proxied(r.provider, r.thumb_url || r.cover_urls[0]), proxied(r.provider, r.cover_urls[0]));
    $("#cover-preview span").textContent = "Esta carátula se descargará al guardar";
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
  const title = form.elements.title.value.trim();
  if (!title) return alert("Escribe primero el título");
  const platform = form.elements.platform_id.selectedOptions[0]?.textContent ?? "";
  $("#cover-picker").hidden = false;
  $("#cover-picker-grid").innerHTML = "";
  $("#cover-picker-status").textContent = "Buscando carátulas…";
  try {
    const { options, errors } = await api(`/api/covers/search?q=${encodeURIComponent(title)}&platform=${encodeURIComponent(platform)}`);
    const label = (name) => providers.find((p) => p.name === name)?.label ?? name;
    const failed = Object.entries(errors).map(([name, msg]) => `${label(name)}: ${msg}`);
    const matching = options.filter((o) => o.matches).length;
    $("#cover-picker-status").textContent =
      (options.length ? `${options.length} carátulas (${matching} del mismo título). Pulsa una para elegirla.` : "No se han encontrado carátulas.") +
      (failed.length ? ` · Error en ${failed.join(" · ")}` : "");
    const tile = (o, i) => `<button type="button" class="cover-opt" data-i="${i}" aria-pressed="false" title="${esc(o.title)}${o.release_year ? ` (${o.release_year})` : ""} · ${esc(label(o.provider))}">
        <img src="${esc(proxied(o.provider, o.thumb_url))}" alt="" loading="lazy">
        <span>${esc(label(o.provider))} · ${esc(o.title)}</span>
      </button>`;
    const first = options.findIndex((o) => !o.matches);
    $("#cover-picker-grid").innerHTML = options.map((o, i) =>
      (i === first && matching ? "<h4>Otros resultados</h4>" : "") + tile(o, i)).join("");
    $("#cover-picker-grid").onclick = (ev) => {
      const el = ev.target.closest(".cover-opt");
      if (!el) return;
      const o = options[Number(el.dataset.i)];
      document.querySelectorAll(".cover-opt").forEach((b) => b.setAttribute("aria-pressed", String(b === el)));
      form.elements.cover.value = "";
      pendingCover = { provider: o.provider, urls: o.urls };
      showCover(proxied(o.provider, o.thumb_url), proxied(o.provider, o.urls[0]));
      $("#cover-preview span").textContent = `Carátula de ${label(o.provider)}: se descargará al guardar`;
    };
  } catch (err) {
    $("#cover-picker-status").textContent = err.message;
  }
}

const money = (n) => n.toLocaleString("es-ES", { style: "currency", currency: "EUR" });

function bars(title, data, labels = {}) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  if (!entries.length) return "";
  const max = Math.max(...entries.map(([, n]) => n));
  return `<section class="panel"><h3>${esc(title)}</h3>${entries.map(([k, n]) => `
    <div class="bar-row" title="${esc(labels[k] ?? k)}: ${n}">
      <span class="bar-label">${esc(labels[k] ?? k)}</span>
      <span class="bar-track"><span class="bar" style="width:${(n / max) * 100}%"></span></span>
      <span class="bar-value">${n}</span>
    </div>`).join("")}</section>`;
}

async function loadStats() {
  const s = await api("/api/stats");
  $("#stats").textContent =
    `${s.collection} en colección · ${s.by_format.physical ?? 0} físicos · ${s.by_format.digital ?? 0} digitales`;
  if (tab !== "stats") return;
  $("#stats-view").innerHTML = `
    <div class="tiles">
      <div class="tile"><div class="tile-value">${s.collection}</div><div class="tile-label">En colección</div></div>
      <div class="tile"><div class="tile-value">${s.by_status.wishlist ?? 0}</div><div class="tile-label">En wishlist</div></div>
      <div class="tile"><div class="tile-value">${s.loaned}</div><div class="tile-label">Prestados</div></div>
      <div class="tile"><div class="tile-value">${money(s.total_spent)}</div><div class="tile-label">Gastado</div></div>
    </div>
    <div class="panels">
      ${bars("Por plataforma", s.by_platform)}
      ${bars("Por formato", s.by_format, FORMAT)}
      ${bars("Progreso", s.by_completion, COMPLETION)}
    </div>
    <p class="hint">Las cifras de colección incluyen los prestados; no incluyen wishlist ni vendidos.</p>`;
}

function setTab(name) {
  tab = name;
  document.querySelectorAll(".tabs:not(.dlg-tabs) [role=tab]").forEach((b) => b.setAttribute("aria-selected", b.dataset.tab === name));
  const isStats = name === "stats";
  $("#filters").hidden = isStats;
  $("#grid").hidden = isStats;
  $("#pager").hidden = isStats;
  $("#stats-view").hidden = !isStats;
  if (isStats) { $("#empty").hidden = true; loadStats(); } else loadGames();
}

const PAGE_SIZE = 60;
const list = { loaded: 0, total: 0, gen: 0, loading: false };

const VIEWS = ["grid", "list", "table"];
let view = "grid";
try { if (VIEWS.includes(localStorage.getItem("glm-view"))) view = localStorage.getItem("glm-view"); } catch {}

const badges = (g) =>
  `<span class="badge">${FORMAT[g.format]}</span>${g.item_type ? `<span class="badge">${esc(g.item_type)}</span>` : ""}${g.status !== "owned" ? `<span class="badge">${STATUS[g.status]}</span>` : ""}`;

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

// [sort key, header]; the key is the API's sort field
const COLUMNS = [
  ["title", "Título"], ["platform", "Plataforma"], ["release_year", "Año"], ["format", "Formato"],
  ["status", "Estado"], ["completion", "Progreso"], ["store", "Tienda"], ["purchase_date", "Fecha compra"],
  ["purchase_price", "Precio"], ["rating", "Nota"],
];

function tableHead() {
  const sort = $("#sort").value;
  const th = ([key, label]) => {
    const dir = sort === key ? "asc" : sort === `-${key}` ? "desc" : null;
    return `<th data-sort="${key}"${dir ? ` aria-sort="${dir === "asc" ? "ascending" : "descending"}"` : ""} title="Ordenar por ${label}">${label}${dir ? (dir === "asc" ? " ▲" : " ▼") : ""}</th>`;
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
    option.textContent = `${COLUMNS.find(([k]) => k === key)[1]} ${value.startsWith("-") ? "▼" : "▲"}`;
  }
  select.value = value;
  loadGames();
}

const rowHtml = (g) => `
    <tr data-id="${g.id}">
      <td class="c">${g.cover_url ? `<img src="${esc(g.cover_url)}" alt="" loading="lazy">` : "<span>🎮</span>"}</td>
      <td class="t">${esc(g.title)}${g.item_type ? ` <span class="badge">${esc(g.item_type)}</span>` : ""}</td>
      <td>${esc(g.platform.name)}</td>
      <td class="num">${g.release_year ?? ""}</td>
      <td>${FORMAT[g.format]}</td>
      <td>${STATUS[g.status]}${g.loaned_to ? ` → ${esc(g.loaned_to)}` : ""}</td>
      <td>${COMPLETION[g.completion] ?? ""}</td>
      <td>${esc(g.store)}</td>
      <td class="num">${esc(g.purchase_date)}</td>
      <td class="num">${g.purchase_price != null ? money(g.purchase_price) : ""}</td>
      <td class="num">${g.rating != null ? `${g.rating}/10` : ""}</td>
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
  for (const status of TAB_STATUS[tab] ?? []) params.append("status", status);
  return params;
}

function renderPager() {
  const pages = Math.max(1, Math.ceil(list.total / PAGE_SIZE));
  const page = Math.min(pages, Math.max(1, Math.ceil(list.loaded / PAGE_SIZE)));
  const more = list.loaded < list.total;
  $("#pager").hidden = list.total === 0 || tab === "stats";
  $("#pager-info").textContent = `Mostrando ${list.loaded} de ${list.total} · página ${page} de ${pages}`;
  $("#more-btn").hidden = !more;
  $("#more-btn").disabled = list.loading;
  $("#more-btn").textContent = list.loading ? "Cargando…" : "Cargar más";
}

// Fetches the next page and appends it. A filter change bumps list.gen, so a page that
// arrives for an old filter is dropped instead of being mixed into the new list.
async function loadMore() {
  if (list.loading || (list.loaded && list.loaded >= list.total)) return;
  const gen = list.gen;
  list.loading = true;
  renderPager();
  try {
    const params = listParams();
    params.set("limit", PAGE_SIZE);
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
  await loadMore();
  while (list.loaded < Math.min(target, list.total) && !list.loading) {
    const before = list.loaded;
    await loadMore();
    if (list.loaded === before) break;
  }
}

new IntersectionObserver((entries) => {
  if (entries.some((e) => e.isIntersecting) && tab !== "stats") loadMore();
}, { rootMargin: "400px" }).observe($("#pager"));

const refresh = () => Promise.all([tab === "stats" ? null : loadGames(true), loadStats()]);

function setPane(name) {
  document.querySelectorAll(".dlg-tabs [role=tab]").forEach((b) => b.setAttribute("aria-selected", b.dataset.pane === name));
  document.querySelectorAll("#game-form .pane").forEach((p) => { p.hidden = p.dataset.pane !== name; });
}

function openDialog(game) {
  const form = $("#game-form");
  form.reset();
  pendingCover = null;
  $("#lookup").hidden = true;
  $("#cover-preview").hidden = !game?.cover_url;
  $("#cover-picker").hidden = true;
  if (game?.cover_url) {
    showCover(game.cover_url);
    $("#cover-preview span").textContent = "Carátula actual";
  }
  $("#dlg-title").textContent = game ? "Editar juego" : "Añadir juego";
  $("#delete-btn").hidden = !game;
  form.elements.id.value = game?.id ?? "";
  if (game) {
    for (const el of form.elements) {
      if (el.name && !SKIP_FIELDS.has(el.name) && game[el.name] != null) el.value = String(game[el.name]);
    }
  }
  setPane("general");
  $("#scrape-info").textContent = game?.scraped_at
    ? `Última búsqueda online: ${game.scraped_at.slice(0, 16).replace("T", " ")}${game.scrape_error ? ` · ${game.scrape_error}` : ""}`
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
        alert(`Juego guardado, pero no se pudo descargar la carátula: ${err.message}`);
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
  if (!confirm("¿Eliminar este juego?")) return;
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
  $("#cover-preview span").textContent = "Esta imagen se subirá al guardar";
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
    let msg = `${r.imported} importados, ${r.skipped} omitidos (duplicados o sin título).`;
    if (r.errors.length) msg += `\n\nErrores:\n` + r.errors.slice(0, 10).map((e) => `Fila ${e.row}: ${e.message}`).join("\n");
    if (r.unmapped_columns.length) msg += `\n\nColumnas ignoradas: ${r.unmapped_columns.join(", ")}`;
    alert(msg);
    $("#f-platform").length = 1;
    await loadPlatforms();
    refresh();
  } catch (err) {
    alert(err.message);
  }
});
$("#steam-import-btn").addEventListener("click", async () => {
  if (!confirm("¿Importar tu biblioteca de Steam? Los juegos ya importados se omiten.")) return;
  try {
    const r = await api("/api/import/steam", { method: "POST" });
    alert(`${r.imported} juegos importados, ${r.skipped} ya estaban. Las carátulas se descargan en segundo plano.`);
    refresh();
  } catch (err) {
    alert(err.message);
  }
});
$("#cancel-btn").addEventListener("click", () => $("#dlg").close());
$("#add-btn").addEventListener("click", () => openDialog(null));
$("#grid").addEventListener("click", async (ev) => {
  const th = ev.target.closest("th[data-sort]");
  if (th) return sortBy(th.dataset.sort);
  const card = ev.target.closest("[data-id]");
  if (card) openDialog(await api(`/api/games/${card.dataset.id}`));
});

let debounce;
$("#q").addEventListener("input", () => { clearTimeout(debounce); debounce = setTimeout(() => loadGames(), 250); });
for (const sel of ["#f-platform", "#f-format", "#sort"]) $(sel).addEventListener("change", () => loadGames());
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
  const counts = (st.want_covers ? `${st.covers} carátulas nuevas · ` : "") +
    (st.want_details ? `${st.details} con datos nuevos · ` : "") +
    `${st.found} encontrados · ${st.not_found} sin resultados` +
    (st.failed ? ` · ${st.failed} con error` : "");
  bar.querySelector(".scrape-text").textContent = st.running
    ? `Buscando en ${st.sources.join(", ")} ${st.done}/${st.total}${st.current ? ` · ${st.current}` : ""} · ${counts}`
    : `${st.cancelled ? "Búsqueda cancelada" : "Búsqueda terminada"}: ${st.done}/${st.total} · ${counts}` +
      (st.errors.length ? ` · Errores: ${st.errors.slice(0, 3).join(" | ")}` : "");
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
  // Remember which sources were unticked, so a newly configured source starts ticked
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem("glm-scrape-prefs") || "{}"); } catch {}
  $("#scrape-providers").innerHTML = enabled.map((p) =>
    `<label class="radio"><input type="checkbox" name="provider" value="${esc(p.name)}"${(saved.excluded ?? []).includes(p.name) ? "" : " checked"}> ${esc(p.label)}</label>`,
  ).join("") || "Ninguna fuente activa.";
  $("#scrape-providers-hint").hidden = enabled.length > 1;
  const form = $("#scrape-form").elements;
  if (saved.covers !== undefined) form.covers.checked = saved.covers;
  if (saved.details !== undefined) form.details.checked = saved.details;
  $("#scrape-missing-label").textContent = `Solo los que nunca se han buscado (${st.never_scraped})`;
  $("#scrape-all-label").textContent = `Todos (${st.library_total})`;
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
  if (!body.providers.length) return alert("Elige al menos una fuente");
  if (!body.covers && !body.details) return alert("Elige carátula, datos o ambos");
  try { localStorage.setItem("glm-scrape-prefs", JSON.stringify({
    excluded: providers.filter((p) => p.enabled && !body.providers.includes(p.name)).map((p) => p.name),
    covers: body.covers, details: body.details,
  })); } catch {}
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
  const answer = prompt(
    "Se borrarán TODOS los juegos, sus carátulas y las plataformas añadidas. No se puede deshacer.\n" +
    "Si quieres una copia, cancela y usa antes «Exportar CSV».\n\nEscribe BORRAR para confirmar:"
  );
  if (answer === null) return;
  if (answer.trim().toUpperCase() !== "BORRAR") { alert("No se ha borrado nada."); return; }
  try {
    const r = await api("/api/reset", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirm: "BORRAR" }),
    });
    alert(`Biblioteca vacía: ${r.games_deleted} juegos y ${r.platforms_deleted} plataformas añadidas borrados.`);
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
  const built = a.build_date ? ` · compilada ${esc(a.build_date.slice(0, 16).replace("T", " "))} UTC` : "";
  const db = a.database === "postgresql" ? "PostgreSQL" : a.database === "sqlite" ? "SQLite" : a.database;
  $("#about").innerHTML =
    `Game Library Manager v${esc(a.version)}${a.ref ? ` (${esc(a.ref)})` : ""}${commit}${built} · ${esc(db)}, esquema ${esc(a.schema)}`;
}

Promise.all([loadPlatforms(), loadProviders()]).then(refresh);
loadAbout();
api("/api/scrape").then((st) => { if (st.running) pollScrape(); });
