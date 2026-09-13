const ROLES = ["before", "wash", "detail", "after", "hero", "engine", "wheel", "interior", "machine"];
const state = {
  filter: "unlabeled",
  query: "",
  groups: [],
  counts: {},
  cursor: 0,
  items: [],
  current: null,
  draft: { role: "", shoot_day: "", subjects: "", note: "" },
};

async function api(name, opts = {}) {
  const method = opts.method || "GET";
  const url = new URL(`/api/${name}`, window.location.origin);
  if (method === "GET") {
    for (const [key, value] of Object.entries(opts.query || {})) {
      if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, value);
    }
  }
  const res = await fetch(url, {
    method,
    headers: method === "POST" ? { "Content-Type": "application/json" } : undefined,
    body: method === "POST" ? JSON.stringify(opts.body || {}) : undefined,
  });
  return res.json();
}

function keyframeSrc(row) {
  if (!row) return "";
  if (row.keyframe) {
    const name = row.keyframe.split(/[/\\]/).pop();
    return `/keyframes/${encodeURIComponent(name)}`;
  }
  return row.media_id ? `/media/${encodeURIComponent(row.media_id)}/thumb` : "";
}

function proxySrc(row) {
  return row && row.media_id ? `/media/${encodeURIComponent(row.media_id)}/proxy` : "";
}

function flatten(groups) {
  const items = [];
  for (const group of groups) {
    items.push(group.media);
    for (const shot of group.shots || []) items.push(shot);
  }
  return items;
}

function matchesQuery(row) {
  const q = state.query.trim().toLowerCase();
  if (!q) return true;
  const labels = row.labels || {};
  const hay = [
    row.filename,
    row.media_id,
    row.shot_id,
    labels.role && labels.role.value,
    labels.note && labels.note.value,
    ((labels.subjects && labels.subjects.value) || []).join(" "),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return hay.includes(q);
}

function visibleItems() {
  return state.items.filter(matchesQuery);
}

function setDraft(row) {
  const labels = (row && row.labels) || {};
  state.draft = {
    role: (labels.role && labels.role.value) || "",
    shoot_day: labels.shoot_day && labels.shoot_day.value != null ? String(labels.shoot_day.value) : "",
    subjects: ((labels.subjects && labels.subjects.value) || []).join(", "),
    note: (labels.note && labels.note.value) || "",
  };
}

function payloadFromDraft(row) {
  const subjects = state.draft.subjects.split(",").map((s) => s.trim()).filter(Boolean);
  const body = {
    role: state.draft.role || null,
    shoot_day: state.draft.shoot_day === "" ? null : state.draft.shoot_day,
    subjects,
    note: state.draft.note || null,
    source: "owner",
  };
  if (row.scope === "shot" && row.shot_id) body.shot_id = row.shot_id;
  else body.media_id = row.media_id;
  return body;
}

function renderReady(data) {
  const el = document.getElementById("ready");
  if (data.ready) {
    el.textContent = "agent ready";
    el.className = "pill ready";
  } else {
    el.textContent = (data.reasons && data.reasons[0]) || "not ready";
    el.className = "pill warn";
  }
}

function renderCounts(counts) {
  for (const key of ["unlabeled", "needs_confirmation", "conflicts", "all"]) {
    const el = document.getElementById(`c-${key}`);
    if (el) el.textContent = counts[key] || 0;
  }
}

function renderQueue() {
  const root = document.getElementById("queue");
  const q = state.query.trim().toLowerCase();
  root.innerHTML = state.groups
    .map((group) => {
      const rows = [group.media, ...(group.shots || [])].filter(matchesQuery);
      if (!rows.length) return "";
      const day = group.shoot_day == null ? "unassigned" : `day ${group.shoot_day}`;
      return `<div class="group"><h3>${day} · ${group.filename || group.media_id}</h3>${rows
        .map((row) => {
          const idx = visibleItems().indexOf(row);
          const sel = row === state.current ? " sel" : "";
          const labels = row.labels || {};
          const role = (labels.role && labels.role.value) || "unlabeled";
          const klass = row.conflicts && row.conflicts.length ? "bad" : labels.confirmed ? "ok" : labels.needs_confirmation ? "warn" : "";
          const scope = row.scope === "shot" ? `${Number(row.in_s || 0).toFixed(1)}–${Number(row.out_s || 0).toFixed(1)}s` : "file";
          return `<button class="row${sel}" data-idx="${idx}"><span class="dot ${klass}"></span>${role}<small>${scope} · ${row.filename || row.media_id}</small></button>`;
        })
        .join("")}</div>`;
    })
    .join("") || `<p class="muted">${q ? "no matches" : "queue empty"}</p>`;
  root.querySelectorAll(".row").forEach((btn) => {
    btn.addEventListener("click", () => select(Number(btn.dataset.idx)));
  });
}

function renderFilmstrip(group) {
  const strip = document.getElementById("filmstrip");
  const shots = (group && group.shots) || [];
  strip.innerHTML = shots
    .map((shot) => {
      const sel = state.current && state.current.shot_id === shot.shot_id ? " sel" : "";
      const src = keyframeSrc(shot);
      return `<button class="${sel}" data-shot="${shot.shot_id || ""}"><img src="${src}" alt="" /></button>`;
    })
    .join("");
  strip.querySelectorAll("button").forEach((btn) => {
    btn.addEventListener("click", () => {
      const idx = visibleItems().findIndex((row) => row.shot_id === btn.dataset.shot);
      if (idx >= 0) select(idx);
    });
  });
}

function sourceLine(field) {
  if (!field || !field.source) return "";
  return `${field.source}${field.confirmed ? " · confirmed" : " · suggested"}`;
}

function renderInspector(row) {
  const root = document.getElementById("inspector");
  if (!row) {
    root.innerHTML = `<p class="muted">No clip selected.</p>`;
    return;
  }
  const labels = row.labels || {};
  const conflicts = (row.conflicts || []).map((c) => `<div class="conflict">${c}</div>`).join("");
  root.innerHTML = `
    <h2>${row.scope === "shot" ? "Shot" : "File"}</h2>
    <p class="muted">${row.filename || row.media_id}${row.shot_id ? ` · ${row.shot_id}` : ""}</p>
    ${conflicts}
    <label>Role</label>
    <select id="role">${["", ...ROLES].map((r) => `<option value="${r}" ${state.draft.role === r ? "selected" : ""}>${r || "—"}</option>`).join("")}</select>
    <div class="source">${sourceLine(labels.role)}</div>
    <label>Shoot day</label>
    <input id="day" value="${state.draft.shoot_day}" />
    <div class="source">${sourceLine(labels.shoot_day)}</div>
    <label>Subjects</label>
    <input id="subjects" value="${state.draft.subjects}" placeholder="hood, panel" />
    <div class="source">${sourceLine(labels.subjects)}</div>
    <label>Note</label>
    <textarea id="note">${state.draft.note}</textarea>
    <div class="source">${sourceLine(labels.note)}</div>
  `;
  root.querySelector("#role").addEventListener("change", (e) => (state.draft.role = e.target.value));
  root.querySelector("#day").addEventListener("input", (e) => (state.draft.shoot_day = e.target.value));
  root.querySelector("#subjects").addEventListener("input", (e) => (state.draft.subjects = e.target.value));
  root.querySelector("#note").addEventListener("input", (e) => (state.draft.note = e.target.value));
}

function loopShot(video, row) {
  if (!row || row.scope !== "shot" || row.in_s == null || row.out_s == null) return;
  const start = Number(row.in_s);
  const end = Number(row.out_s);
  if (video.currentTime < start || video.currentTime >= end - 0.04) {
    video.currentTime = start;
  }
}

function playRow(row) {
  const video = document.getElementById("video");
  const src = proxySrc(row);
  const start = row && row.in_s != null ? Number(row.in_s) : 0;
  if (video.dataset.src !== src) {
    video.src = src;
    video.dataset.src = src;
    video.onloadedmetadata = () => {
      video.currentTime = start;
      video.play().catch(() => {});
    };
  } else {
    video.currentTime = start;
    video.play().catch(() => {});
  }
  video.ontimeupdate = () => loopShot(video, row);
}

function select(index) {
  const items = visibleItems();
  if (!items.length) {
    state.current = null;
    renderQueue();
    renderInspector(null);
    return;
  }
  state.cursor = (index + items.length) % items.length;
  state.current = items[state.cursor];
  setDraft(state.current);
  const group = state.groups.find((g) => g.media_id === state.current.media_id);
  renderQueue();
  renderFilmstrip(group);
  renderInspector(state.current);
  playRow(state.current);
}

async function refresh() {
  const [queue, ready] = await Promise.all([
    api("label_queue", { query: { filter: state.filter } }),
    api("label_readiness"),
  ]);
  state.groups = queue.groups || [];
  state.items = flatten(state.groups);
  state.counts = queue.counts || {};
  renderCounts(state.counts);
  renderReady(ready);
  const keep = state.current && visibleItems().findIndex((row) => row.media_id === state.current.media_id && row.shot_id === state.current.shot_id);
  select(keep >= 0 ? keep : 0);
}

async function confirmNext() {
  const row = state.current;
  if (!row) return;
  const body = payloadFromDraft(row);
  const name = row.scope === "shot" ? "shot_card_confirm" : "media_card_confirm";
  const result = await api(name, { method: "POST", body });
  if (!result.ok) return;
  await refresh();
  const items = visibleItems();
  if (items.length) select(Math.min(state.cursor, items.length - 1));
}

async function skip() {
  select(state.cursor + 1);
}

async function clearCurrent() {
  const row = state.current;
  if (!row) return;
  const body = row.scope === "shot" ? { shot_id: row.shot_id } : { media_id: row.media_id };
  await api("labels_clear", { method: "POST", body });
  await refresh();
}

async function undo() {
  await api("labels_undo", { method: "POST", body: {} });
  await refresh();
}

function setStatus(text, kind) {
  const el = document.getElementById("status");
  if (!el) return;
  el.textContent = text || "";
  el.className = kind === "bad" ? "conflict" : "muted";
}

async function deleteCurrent() {
  const row = state.current;
  if (!row || !row.media_id) return;
  const name = row.filename || row.media_id;
  if (!window.confirm(`Delete ${name} from this project?`)) return;
  const result = await api("media_remove", { method: "POST", body: { media_id: row.media_id } });
  if (!result.ok) {
    setStatus((result.warnings && result.warnings[0]) || "could not delete", "bad");
    return;
  }
  state.current = null;
  setStatus("");
  await refresh();
}

function bind() {
  document.getElementById("filters").addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-filter]");
    if (!btn) return;
    state.filter = btn.dataset.filter;
    document.querySelectorAll("#filters button").forEach((b) => b.classList.toggle("active", b === btn));
    refresh();
  });
  document.getElementById("search").addEventListener("input", (e) => {
    state.query = e.target.value;
    renderQueue();
  });
  document.getElementById("confirm").addEventListener("click", confirmNext);
  document.getElementById("skip").addEventListener("click", skip);
  document.getElementById("clear").addEventListener("click", clearCurrent);
  document.getElementById("undo").addEventListener("click", undo);
  document.getElementById("delete").addEventListener("click", deleteCurrent);
  document.addEventListener("keydown", (e) => {
    const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement && document.activeElement.tagName);
    if (e.key === "/" && !typing) {
      e.preventDefault();
      document.getElementById("search").focus();
      return;
    }
    if (typing && e.key !== "Enter") return;
    const video = document.getElementById("video");
    if (e.key === " " && !typing) {
      e.preventDefault();
      if (video.paused) video.play();
      else video.pause();
    } else if (e.key === "j") video.currentTime = Math.max(0, video.currentTime - 2);
    else if (e.key === "k") video.paused ? video.play() : video.pause();
    else if (e.key === "l") video.currentTime += 2;
    else if (e.key === "ArrowLeft") select(state.cursor - 1);
    else if (e.key === "ArrowRight") select(state.cursor + 1);
    else if (e.key === "ArrowUp") select(state.cursor - 1);
    else if (e.key === "ArrowDown") select(state.cursor + 1);
    else if (e.key === "Enter") confirmNext();
    else if (e.key === "s" || e.key === "S") skip();
    else if (e.key === "u" || e.key === "U") undo();
    else if (/^[1-9]$/.test(e.key)) {
      state.draft.role = ROLES[Number(e.key) - 1] || "";
      renderInspector(state.current);
    }
  });
}

bind();
refresh();
