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
  if (r.provider === "steam") f.steam_appid.value = r.external_id;
  if (r.cover_urls.length) {
    pendingCover = { provider: r.provider, urls: r.cover_urls };
    $("#cover-preview").hidden = false;
    $("#cover-preview img").src = proxied(r.provider, r.thumb_url || r.cover_urls[0]);
    $("#cover-preview span").textContent = "Esta carátula se descargará al guardar";
  }
  $("#lookup").hidden = true;
}

async function loadStats() {
  const s = await api("/api/stats");
  $("#stats").textContent =
    `${s.total} juegos · ${s.by_format.physical ?? 0} físicos · ${s.by_format.digital ?? 0} digitales`;
}

async function loadGames() {
  const params = new URLSearchParams();
  for (const [key, el] of [["q", "#q"], ["platform_id", "#f-platform"], ["format", "#f-format"], ["status", "#f-status"], ["sort", "#sort"]]) {
    if ($(el).value) params.set(key, $(el).value);
  }
  const page = await api(`/api/games?${params}`);
  $("#empty").hidden = page.total > 0;
  $("#grid").innerHTML = page.items.map((g) => `
    <article class="card" data-id="${g.id}">
      <div class="cover">${g.cover_url ? `<img src="${esc(g.cover_url)}" alt="" loading="lazy">` : "🎮"}</div>
      <div class="info">
        <div class="title">${esc(g.title)}</div>
        <div class="meta">${esc(g.platform.name)}${g.release_year ? " · " + g.release_year : ""}</div>
        <span class="badge">${FORMAT[g.format]}</span>${g.status !== "owned" ? `<span class="badge">${STATUS[g.status]}</span>` : ""}
      </div>
    </article>`).join("");
}

const refresh = () => Promise.all([loadGames(), loadStats()]);

function openDialog(game) {
  const form = $("#game-form");
  form.reset();
  pendingCover = null;
  $("#lookup").hidden = true;
  $("#cover-preview").hidden = true;
  $("#dlg-title").textContent = game ? "Editar juego" : "Añadir juego";
  $("#delete-btn").hidden = !game;
  form.elements.id.value = game?.id ?? "";
  if (game) {
    for (const el of form.elements) {
      if (el.name && !SKIP_FIELDS.has(el.name) && game[el.name] != null) el.value = game[el.name];
    }
  }
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
  for (const key of ["platform_id", "release_year", "steam_appid"]) if (data[key] != null) data[key] = Number(data[key]);
  if (data.purchase_price != null) data.purchase_price = Number(data.purchase_price);

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
  const card = ev.target.closest(".card");
  if (card) openDialog(await api(`/api/games/${card.dataset.id}`));
});

let debounce;
$("#q").addEventListener("input", () => { clearTimeout(debounce); debounce = setTimeout(loadGames, 250); });
for (const sel of ["#f-platform", "#f-format", "#f-status", "#sort"]) $(sel).addEventListener("change", loadGames);

Promise.all([loadPlatforms(), loadProviders()]).then(refresh);
