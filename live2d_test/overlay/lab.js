(() => {
  const $ = (id) => document.getElementById(id);
  const SCENES = {
    auto: { work_mode: "idle", interaction_mode: "chat", talking: false, alert: "none", emotion: { mood: "平静" } },
    work: { work_mode: "executing", interaction_mode: "task", talking: false, alert: "none" },
    think: { work_mode: "deep_tech", interaction_mode: "task", talking: false, alert: "none" },
    wrap: { work_mode: "wrapping_up", interaction_mode: "task", talking: false, alert: "none" },
    look: { work_mode: "idle", interaction_mode: "exploratory", talking: false, alert: "none" },
    talk: { work_mode: "chat", interaction_mode: "chat", talking: true, alert: "none" },
    rest: { work_mode: "idle", interaction_mode: "chat", talking: false, alert: "none", emotion: { mood: "疲惫" } },
  };
  let pushing = false;
  let groups = [];

  function showScale(scale) {
    const pct = Math.round(Number(scale) * 100);
    $("scale-label").textContent = `${pct}%`;
    const slider = $("scale");
    if (document.activeElement !== slider) slider.value = String(pct);
  }

  function markPlaying(name) {
    document.querySelectorAll("#clip-list button[data-clip]").forEach((btn) => {
      btn.classList.toggle("is-playing", btn.dataset.clip === name);
    });
  }

  function sceneOf(state) {
    if (state.talking) return "talk";
    const work = state.work_mode || "idle";
    const interaction = state.interaction_mode || "chat";
    const mood = (state.emotion || {}).mood || "平静";
    if (work === "executing") return "work";
    if (work === "deep_tech" || work === "clarifying") return "think";
    if (work === "wrapping_up") return "wrap";
    if (interaction === "exploratory") return "look";
    if (mood === "疲惫") return "rest";
    return "auto";
  }

  function show(data) {
    $("through").checked = !!data.click_through;
    $("ontop").checked = data.on_top !== false;
    if (typeof data.scale === "number") showScale(data.scale);
    const clip = data.clip || {};
    const now = $("now-playing");
    if (now) {
      const n = clip.name || "（还没播）";
      const k = clip.kind ? ` · ${clip.kind}` : "";
      const pin = data.pinned ? " · 固定" : "";
      now.textContent = n + k + pin;
    }
    markPlaying(clip.name || "");
    if (!pushing && document.activeElement !== $("scene")) {
      $("scene").value = sceneOf(data.state || {});
    }
  }

  async function post(path, body) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    return res.json();
  }

  function renderClips() {
    const root = $("clip-list");
    if (!root) return;
    const q = ($("clip-filter").value || "").trim().toLowerCase();
    root.innerHTML = "";
    groups.forEach((group) => {
      const clips = (group.clips || []).filter((c) => !q || String(c.name).toLowerCase().includes(q));
      if (!clips.length) return;
      const wrap = document.createElement("div");
      wrap.className = "clip-group";
      const title = document.createElement("h3");
      title.textContent = `${group.label} · ${clips.length}`;
      wrap.appendChild(title);
      const row = document.createElement("div");
      row.className = "row";
      clips.forEach((clip) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.dataset.clip = clip.name;
        btn.textContent = clip.name;
        btn.addEventListener("click", async () => {
          const data = await post("/api/play", { name: clip.name });
          show(data);
        });
        row.appendChild(btn);
      });
      wrap.appendChild(row);
      root.appendChild(wrap);
    });
  }

  $("restore").addEventListener("click", () => post("/api/window", { action: "restore" }));
  $("through").addEventListener("change", () => post("/api/window", { click_through: $("through").checked }));
  $("ontop").addEventListener("change", () => post("/api/window", { on_top: $("ontop").checked }));
  $("scale").addEventListener("input", () => {
    const scale = Number($("scale").value) / 100;
    showScale(scale);
    post("/api/window", { scale });
  });
  $("clip-auto").addEventListener("click", async () => {
    pushing = true;
    try {
      $("scene").value = "auto";
      await post("/api/state", SCENES.auto);
      const data = await post("/api/play", { auto: true });
      show(data);
    } finally {
      pushing = false;
    }
  });
  $("scene").addEventListener("change", async () => {
    if (pushing) return;
    const key = $("scene").value;
    const patch = SCENES[key];
    if (!patch) return;
    pushing = true;
    try {
      let data = await post("/api/state", patch);
      if (key === "auto") data = await post("/api/play", { auto: true });
      else if (key === "rest") data = await post("/api/play", { name: "哈欠连天" });
      show(data);
    } finally {
      pushing = false;
    }
  });
  $("clip-filter").addEventListener("input", renderClips);
  document.querySelectorAll("[data-quick],[data-clip]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const clip = btn.getAttribute("data-clip");
      const data = clip
        ? await post("/api/play", { name: clip })
        : await post("/api/event", { type: "playful_interaction" });
      show(data);
    });
  });

  async function poll() {
    try {
      const data = await (await fetch("/api/state")).json();
      if (!groups.length) {
        groups = (data.catalog && (data.catalog.themes || data.catalog.groups)) || [];
        renderClips();
      }
      show(data);
    } catch {
      /* ignore */
    }
  }

  fetch("/api/catalog")
    .then((res) => res.json())
    .then((data) => {
      groups = data.themes || data.groups || [];
      renderClips();
    })
    .catch(() => {});

  poll();
  setInterval(poll, 400);
})();
