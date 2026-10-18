const $ = (sel) => document.querySelector(sel);
const FORMAT = { physical: "Físico", digital: "Digital" };
const STATUS = { owned: "En colección", wishlist: "Wishlist", lent: "Prestado", sold: "Vendido" };

const api = async (path, opts = {}) => {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.status === 204 ? null : res.json();
};

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

async function loadPlatforms() {
  const platforms = await api("/api/platforms");
  const options = platforms.map((p) => `<option value="${p.id}">${esc(p.name)}</option>`).join("");
  $("#f-platform").insertAdjacentHTML("beforeend", options);
  $("#game-form [name=platform_id]").innerHTML = options;
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
  $("#dlg-title").textContent = game ? "Editar juego" : "Añadir juego";
  $("#delete-btn").hidden = !game;
  form.elements.id.value = game?.id ?? "";
  if (game) {
    for (const el of form.elements) {
      if (el.name && el.name !== "cover" && el.name !== "id" && game[el.name] != null) el.value = game[el.name];
    }
  }
  $("#dlg").showModal();
}

$("#game-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const form = ev.target;
  const data = {};
  for (const el of form.elements) {
    if (!el.name || el.name === "cover" || el.name === "id") continue;
    data[el.name] = el.value === "" ? null : el.value;
  }
  for (const key of ["platform_id", "release_year"]) if (data[key] != null) data[key] = Number(data[key]);
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

$("#cancel-btn").addEventListener("click", () => $("#dlg").close());
$("#add-btn").addEventListener("click", () => openDialog(null));
$("#grid").addEventListener("click", async (ev) => {
  const card = ev.target.closest(".card");
  if (card) openDialog(await api(`/api/games/${card.dataset.id}`));
});

let debounce;
$("#q").addEventListener("input", () => { clearTimeout(debounce); debounce = setTimeout(loadGames, 250); });
for (const sel of ["#f-platform", "#f-format", "#f-status", "#sort"]) $(sel).addEventListener("change", loadGames);

loadPlatforms().then(refresh);
