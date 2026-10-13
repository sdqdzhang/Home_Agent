(() => {
  const video = document.getElementById("clip");
  const hud = document.getElementById("hud");
  let playId = -1;
  let endedBound = false;

  if (new URLSearchParams(location.search).get("transparent") === "1") {
    document.body.classList.add("is-transparent");
  }

  function petApi() {
    return (window.pywebview && pywebview.api) || null;
  }

  async function api(path, opts) {
    const res = await fetch(path, opts);
    return res.json();
  }

  function setPeek(side) {
    video.classList.remove("is-peek-left", "is-peek-right", "is-peek-out");
    if (side === "left") video.classList.add("is-peek-left");
    else if (side === "right") video.classList.add("is-peek-right");
    else if (side === "out") video.classList.add("is-peek-out");
  }

  function play(clip) {
    if (!clip || !clip.url) return;
    if (clip.play_id === playId) return;
    playId = clip.play_id;
    if (hud) {
      hud.hidden = false;
      hud.textContent = clip.name || "";
    }
    video.loop = false;
    video.src = clip.url;
    try {
      video.load();
    } catch {
      /* ignore */
    }
    video.onerror = () => {
      if (hud) hud.textContent = `视频失败: ${clip.name || clip.url}`;
    };
    const start = () => {
      video.play().catch(() => {});
    };
    if (video.readyState >= 2) start();
    else video.onloadeddata = start;
    video.onloadedmetadata = () => {
      const bridge = petApi();
      if (clip.want_walk && clip.kind === "move" && bridge && bridge.begin_walk) {
        bridge.begin_walk(video.duration || 0);
      }
    };
  }

  function onEnded() {
    const bridge = petApi();
    if (bridge && bridge.on_ended) {
      Promise.resolve(bridge.on_ended()).then((data) => {
        if (data && data.clip) play(data.clip);
      });
      return;
    }
    api("/api/ended", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }).then((data) => {
      if (data && data.clip) play(data.clip);
    });
  }

  if (!endedBound) {
    endedBound = true;
    video.addEventListener("ended", onEnded);
    video.addEventListener("timeupdate", () => {
      const bridge = petApi();
      if (bridge && bridge.walk_tick) bridge.walk_tick(video.currentTime || 0);
    });
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) video.pause();
      else video.play().catch(() => {});
    });
  }

  async function poll() {
    try {
      const data = await api("/api/state");
      if (data.clip) play(data.clip);
    } catch {
      /* host not up */
    }
  }

  window.__play = play;
  window.__setPeek = setPeek;
  window.__setScale = () => {};

  poll();
  setInterval(poll, 400);
})();
