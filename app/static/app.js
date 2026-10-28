/* Bayaan — front-end. No framework, no build step: the whole app is this file
   plus style.css. State lives in one object; every render reads from it. */

(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);

  const state = {
    token: localStorage.getItem("bayaan.token") || "",
    user: null,
    models: [],
    modelId: "",
    backend: "local",
    capabilities: null,
    runs: [],
    saved: [],
    busy: false,
    authMode: "login",
  };

  // ── tiny helpers ───────────────────────────────────────────────────────────
  const fmt = (n) => new Intl.NumberFormat("en-US").format(n);

  function toast(message, isError = false) {
    const el = $("toast");
    el.textContent = message;
    el.classList.toggle("is-error", isError);
    el.hidden = false;
    clearTimeout(toast._t);
    toast._t = setTimeout(() => (el.hidden = true), 3200);
  }

  function banner(html) {
    const el = $("banner");
    if (!html) {
      el.hidden = true;
      return;
    }
    el.innerHTML = html;
    el.hidden = false;
  }

  async function api(path, options = {}) {
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    if (state.token) headers.Authorization = `Bearer ${state.token}`;

    const res = await fetch(path, { ...options, headers });

    if (res.status === 204) return null;

    const text = await res.text();
    let body = null;
    try {
      body = text ? JSON.parse(text) : null;
    } catch {
      body = { detail: text.slice(0, 300) };
    }

    if (!res.ok) {
      // FastAPI validation errors arrive as a list of {loc, msg}.
      let detail = body && body.detail;
      if (Array.isArray(detail)) {
        detail = detail.map((d) => `${(d.loc || []).slice(-1)[0]}: ${d.msg}`).join("; ");
      }
      const err = new Error(detail || `Request failed (${res.status})`);
      err.status = res.status;
      throw err;
    }
    return body;
  }

  // ── auth ───────────────────────────────────────────────────────────────────
  function setAuthMode(mode) {
    state.authMode = mode;
    const isRegister = mode === "register";
    $("auth-title").textContent = isRegister ? "Create an account" : "Sign in";
    $("auth-submit").textContent = isRegister ? "Create account" : "Sign in";
    $("auth-toggle").textContent = isRegister ? "I already have an account" : "Create an account";
    $("name-field").hidden = !isRegister;
    $("auth-error").hidden = true;
  }

  function openAuth(mode = "login") {
    setAuthMode(mode);
    $("auth-dialog").showModal();
  }

  async function submitAuth(event) {
    event.preventDefault();
    const email = $("auth-email").value.trim();
    const password = $("auth-password").value;
    const display_name = $("auth-name").value.trim();
    const errEl = $("auth-error");
    errEl.hidden = true;

    const path = state.authMode === "register" ? "/api/auth/register" : "/api/auth/login";
    const payload =
      state.authMode === "register" ? { email, display_name, password } : { email, password };

    try {
      const data = await api(path, { method: "POST", body: JSON.stringify(payload) });
      state.token = data.access_token;
      state.user = data.user;
      localStorage.setItem("bayaan.token", state.token);
      $("auth-dialog").close();
      $("auth-form").reset();
      renderAuth();
      await Promise.all([loadHistory(), loadSaved()]);
      toast(`Welcome, ${data.user.display_name}.`);
    } catch (err) {
      errEl.textContent = err.message;
      errEl.hidden = false;
    }
  }

  function signOut() {
    state.token = "";
    state.user = null;
    state.runs = [];
    state.saved = [];
    localStorage.removeItem("bayaan.token");
    renderAuth();
    renderHistory();
    renderSaved();
    renderStats(null);
    toast("Signed out.");
  }

  function renderAuth() {
    const btn = $("btn-auth");
    if (state.user) {
      btn.textContent = state.user.display_name;
      btn.onclick = signOut;
      btn.title = "Click to sign out";
    } else {
      btn.textContent = "Sign in";
      btn.onclick = () => openAuth("login");
      btn.title = "";
    }
  }

  async function restoreSession() {
    // renderAuth() must run even when there's no token — it's what attaches the
    // click handler to the sign-in button. Returning early here left the button
    // dead on a first visit, which is exactly how a "nothing happens" bug starts.
    if (state.token) {
      try {
        state.user = await api("/api/auth/me");
      } catch {
        state.token = "";
        localStorage.removeItem("bayaan.token");
      }
    }
    renderAuth();
  }

  // ── models ─────────────────────────────────────────────────────────────────
  async function loadModels() {
    state.models = await api("/api/models");
    const select = $("model-select");
    select.innerHTML = "";

    for (const m of state.models) {
      const opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = `${m.label} · ${m.params}`;
      select.appendChild(opt);
    }

    state.modelId = state.models[0]?.id || "";
    select.value = state.modelId;
    $("model-count").textContent = `${state.models.length} models`;
    renderModelCard();
    updateBudget();
  }

  function currentModel() {
    return state.models.find((m) => m.id === state.modelId) || null;
  }

  function renderModelCard() {
    const m = currentModel();
    const card = $("model-card");
    if (!m) {
      card.innerHTML = "";
      return;
    }
    const rows = [
      ["Family", m.family],
      ["Parameters", m.params],
      ["Context", `${fmt(m.context_window)} tokens`],
      ["License", m.license],
    ];
    card.innerHTML =
      rows
        .map(
          ([k, v]) =>
            `<div class="mc-row"><span>${k}</span><span class="mono">${escapeHtml(String(v))}</span></div>`,
        )
        .join("") + `<div class="mc-notes">${escapeHtml(m.notes)}</div>`;
  }

  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  }

  // ── capabilities / backend pill ────────────────────────────────────────────
  async function loadCapabilities() {
    state.capabilities = await api("/api/models/capabilities");
    const c = state.capabilities;
    const pill = $("backend-pill");

    if (c.active_backend === "inspector") {
      pill.textContent = "inspector mode";
      pill.className = "pill pill-warn";
      banner(
        "<strong>No model is connected.</strong> Runs use the built-in prompt inspector — " +
          "it analyses your prompt for real (token budget, template, structure, risks) but it " +
          "does <em>not</em> generate text. Set <code>OLLAMA_BASE_URL</code> or " +
          "<code>CLOUD_API_KEY</code> to connect a real model.",
      );
    } else {
      pill.textContent = c.active_backend;
      pill.className = "pill pill-ok";
      banner("");
    }

    $("backend-hint").textContent =
      c.active_backend === "inspector"
        ? "No backend configured — the inspector answers instead."
        : `Serving from ${c.active_backend}.`;
  }

  // ── budget ─────────────────────────────────────────────────────────────────
  let budgetTimer = null;
  function updateBudget() {
    clearTimeout(budgetTimer);
    budgetTimer = setTimeout(doBudget, 220);
  }

  async function doBudget() {
    const m = currentModel();
    if (!m) return;
    try {
      const b = await api("/api/models/budget", {
        method: "POST",
        body: JSON.stringify({
          model_id: m.id,
          system_prompt: $("system_prompt").value,
          user_prompt: $("user_prompt").value,
          max_tokens: Number($("max_tokens").value),
        }),
      });

      $("b-prompt").textContent = fmt(b.prompt_tokens);
      $("b-reserved").textContent = fmt(b.reserved_for_completion);
      $("b-window").textContent = fmt(b.context_window);
      $("b-used").textContent = fmt(b.total_needed);

      const pct = Math.min(100, Math.round(b.utilization_pct));
      const fill = $("budget-fill");
      fill.style.width = `${pct}%`;
      fill.className = "budget-fill" + (pct > 95 ? " is-bad" : pct > 75 ? " is-warn" : "");

      $("budget-note").textContent = b.fits
        ? `${pct}% of the window used — ${fmt(b.headroom)} tokens spare.`
        : `Over budget by ${fmt(Math.abs(b.headroom))} tokens. Shorten the prompt or lower max tokens.`;
    } catch {
      /* budget is advisory; a failure here shouldn't block the playground */
    }
  }

  // ── running ────────────────────────────────────────────────────────────────
  function payload() {
    return {
      model_id: state.modelId,
      backend: state.backend,
      system_prompt: $("system_prompt").value,
      user_prompt: $("user_prompt").value,
      temperature: Number($("temperature").value),
      top_p: Number($("top_p").value),
      max_tokens: Number($("max_tokens").value),
    };
  }

  function setBusy(busy) {
    state.busy = busy;
    for (const id of ["btn-run", "btn-stream", "btn-compare"]) $(id).disabled = busy;
  }

  function showOutput(text, isError = false) {
    const out = $("output");
    out.textContent = text;
    out.classList.toggle("is-error", isError);
  }

  async function runOnce() {
    if (!requireAuth()) return;
    if (!requirePrompt()) return;

    setBusy(true);
    showOutput("Running…");
    $("run-meta").textContent = "";

    try {
      const run = await api("/api/runs", { method: "POST", body: JSON.stringify(payload()) });
      showOutput(run.output || "(empty response)");
      $("run-meta").textContent =
        `${run.model_label} · ${run.backend} · ${run.latency_ms} ms · ` +
        `${fmt(run.completion_tokens)} tokens` +
        (run.simulated ? " · inspector (not generated)" : "");
      await Promise.all([loadHistory(), loadStats()]);
    } catch (err) {
      showOutput(err.message, true);
      $("run-meta").textContent = "";
    } finally {
      setBusy(false);
    }
  }

  async function runStream() {
    if (!requireAuth()) return;
    if (!requirePrompt()) return;

    setBusy(true);
    showOutput("");
    $("run-meta").textContent = "streaming…";

    try {
      const res = await fetch("/api/runs/stream", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${state.token}`,
        },
        body: JSON.stringify(payload()),
      });

      if (!res.ok) {
        const body = await res.text();
        let detail = body;
        try {
          detail = JSON.parse(body).detail || body;
        } catch {
          /* keep raw */
        }
        throw new Error(detail || `Request failed (${res.status})`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let acc = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const events = buffer.split("\n\n");
        buffer = events.pop() || "";

        for (const evt of events) {
          const line = evt.split("\n").find((l) => l.startsWith("data: "));
          if (!line) continue;
          let msg;
          try {
            msg = JSON.parse(line.slice(6));
          } catch {
            continue;
          }

          if (msg.type === "delta") {
            acc += msg.text;
            showOutput(acc);
          } else if (msg.type === "done") {
            $("run-meta").textContent = `streamed · ${msg.latency_ms} ms`;
          } else if (msg.type === "error") {
            showOutput(acc + `\n\n[error] ${msg.message}`, true);
          }
        }
      }

      if (!acc) showOutput("(the backend returned no text)", true);
      await Promise.all([loadHistory(), loadStats()]);
    } catch (err) {
      showOutput(err.message, true);
    } finally {
      setBusy(false);
    }
  }

  async function runCompare() {
    if (!requireAuth()) return;
    if (!requirePrompt()) return;

    const others = state.models.filter((m) => m.id !== state.modelId).slice(0, 1);
    if (!others.length) {
      toast("Need at least two models in the catalog to compare.", true);
      return;
    }
    const ids = [state.modelId, others[0].id];

    setBusy(true);
    $("compare-wrap").hidden = false;
    $("compare-grid").innerHTML = `<p class="muted small">Running ${ids.length} models…</p>`;

    try {
      const qs = ids.map((id) => `model_ids=${encodeURIComponent(id)}`).join("&");
      const runs = await api(`/api/runs/compare?${qs}`, {
        method: "POST",
        body: JSON.stringify(payload()),
      });

      $("compare-grid").innerHTML = runs
        .map(
          (r) => `
          <div class="compare-col">
            <header>${escapeHtml(r.model_label)} <span class="muted small">· ${r.latency_ms} ms</span></header>
            <pre>${escapeHtml(r.output || "(empty)")}</pre>
          </div>`,
        )
        .join("");

      await Promise.all([loadHistory(), loadStats()]);
    } catch (err) {
      $("compare-grid").innerHTML = `<p class="error">${escapeHtml(err.message)}</p>`;
    } finally {
      setBusy(false);
    }
  }

  function requireAuth() {
    if (state.token) return true;
    openAuth("login");
    toast("Sign in first — runs are saved to your account.", true);
    return false;
  }

  function requirePrompt() {
    if ($("user_prompt").value.trim()) return true;
    toast("Write a user prompt first.", true);
    $("user_prompt").focus();
    return false;
  }

  // ── history / stats / saved ────────────────────────────────────────────────
  async function loadHistory() {
    if (!state.token) return;
    try {
      state.runs = await api("/api/runs?limit=25");
      renderHistory();
    } catch {
      /* silent — history is secondary */
    }
  }

  function renderHistory() {
    const ul = $("history");
    ul.innerHTML = "";
    if (!state.runs.length) {
      ul.innerHTML = `<li class="empty">No runs yet.</li>`;
      return;
    }
    for (const r of state.runs) {
      const li = document.createElement("li");
      li.innerHTML = `
        <span class="h-model">${escapeHtml(r.model_label)}</span>
        <span class="h-prompt">${escapeHtml(r.user_prompt.slice(0, 90))}</span>
        <span class="h-meta">${r.latency_ms} ms · ${r.backend}${r.simulated ? " · inspector" : ""}</span>`;
      li.onclick = () => loadRun(r.id);
      ul.appendChild(li);
    }
  }

  async function loadRun(id) {
    try {
      const run = await api(`/api/runs/${id}`);
      $("system_prompt").value = run.system_prompt;
      $("user_prompt").value = run.user_prompt;
      $("temperature").value = run.temperature;
      $("top_p").value = run.top_p;
      $("max_tokens").value = run.max_tokens;
      state.modelId = run.model_id;
      $("model-select").value = run.model_id;
      syncSliders();
      renderModelCard();
      updateBudget();
      showOutput(run.output || "(empty)");
      $("run-meta").textContent = `${run.model_label} · ${run.latency_ms} ms · ${run.status}`;
    } catch (err) {
      toast(err.message, true);
    }
  }

  async function loadStats() {
    if (!state.token) return;
    try {
      renderStats(await api("/api/runs/stats/summary"));
    } catch {
      /* ignore */
    }
  }

  function renderStats(s) {
    const el = $("stats");
    if (!s) {
      el.innerHTML = "";
      return;
    }
    const cells = [
      ["Runs", fmt(s.total_runs)],
      ["Avg latency", `${fmt(s.avg_latency_ms)} ms`],
      ["Tokens", fmt(s.total_tokens)],
      ["Top model", s.top_model ? s.top_model.split(" ")[0] : "—"],
    ];
    el.innerHTML = cells
      .map(
        ([k, v]) =>
          `<div><span class="stat-val">${escapeHtml(String(v))}</span><span class="stat-key">${k}</span></div>`,
      )
      .join("");
  }

  async function loadSaved() {
    if (!state.token) return;
    try {
      state.saved = await api("/api/prompts");
      renderSaved();
    } catch {
      /* ignore */
    }
  }

  function renderSaved() {
    const ul = $("saved");
    ul.innerHTML = "";
    if (!state.saved.length) {
      ul.innerHTML = `<li class="empty">Nothing saved yet.</li>`;
      return;
    }
    for (const p of state.saved) {
      const li = document.createElement("li");
      li.innerHTML = `
        <span class="h-model">${escapeHtml(p.name)}</span>
        <span class="h-prompt">${escapeHtml((p.user_prompt || "").slice(0, 80) || "—")}</span>`;
      li.onclick = () => {
        $("system_prompt").value = p.system_prompt;
        $("user_prompt").value = p.user_prompt;
        updateBudget();
        toast(`Loaded "${p.name}".`);
      };
      ul.appendChild(li);
    }
  }

  async function savePrompt() {
    if (!requireAuth()) return;
    const name = prompt("Name this prompt:", $("user_prompt").value.slice(0, 40) || "Untitled");
    if (!name) return;
    try {
      await api("/api/prompts", {
        method: "POST",
        body: JSON.stringify({
          name,
          system_prompt: $("system_prompt").value,
          user_prompt: $("user_prompt").value,
        }),
      });
      await loadSaved();
      toast("Saved.");
    } catch (err) {
      toast(err.message, true);
    }
  }

  // ── template viewer ────────────────────────────────────────────────────────
  async function showTemplate() {
    const m = currentModel();
    if (!m) return;
    try {
      const t = await api(`/api/models/${encodeURIComponent(m.id)}/template`);
      $("template-title").textContent = `${m.label} — ${t.template_name}`;
      $("template-note").textContent = t.note || "";
      $("template-body").textContent = t.template;
      $("template-dialog").showModal();
    } catch (err) {
      toast(err.message, true);
    }
  }

  // ── sliders ────────────────────────────────────────────────────────────────
  function syncSliders() {
    $("temp-out").textContent = Number($("temperature").value).toFixed(2);
    $("topp-out").textContent = Number($("top_p").value).toFixed(2);
    $("maxtok-out").textContent = $("max_tokens").value;
  }

  // ── wiring ─────────────────────────────────────────────────────────────────
  function wire() {
    $("model-select").addEventListener("change", (e) => {
      state.modelId = e.target.value;
      renderModelCard();
      updateBudget();
    });

    for (const id of ["temperature", "top_p", "max_tokens"]) {
      $(id).addEventListener("input", () => {
        syncSliders();
        updateBudget();
      });
    }

    $("user_prompt").addEventListener("input", () => {
      $("char-count").textContent = fmt($("user_prompt").value.length);
      updateBudget();
    });
    $("system_prompt").addEventListener("input", updateBudget);

    document.querySelectorAll(".seg").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".seg").forEach((b) => b.classList.remove("is-active"));
        btn.classList.add("is-active");
        state.backend = btn.dataset.backend;
      });
    });

    $("btn-run").onclick = runOnce;
    $("btn-stream").onclick = runStream;
    $("btn-compare").onclick = runCompare;
    $("btn-save").onclick = savePrompt;
    $("btn-template").onclick = showTemplate;
    $("btn-refresh").onclick = () => Promise.all([loadHistory(), loadStats(), loadSaved()]);
    $("btn-clear").onclick = () => {
      $("system_prompt").value = "";
      $("user_prompt").value = "";
      $("char-count").textContent = "0";
      showOutput("Nothing yet. Write a prompt and hit Run.");
      $("run-meta").textContent = "";
      $("compare-wrap").hidden = true;
      updateBudget();
    };

    $("auth-form").addEventListener("submit", submitAuth);
    $("auth-toggle").onclick = () => setAuthMode(state.authMode === "login" ? "register" : "login");
    $("auth-cancel").onclick = () => $("auth-dialog").close();
    $("template-close").onclick = () => $("template-dialog").close();

    // Ctrl/Cmd+Enter runs the prompt — the shortcut every playground has.
    document.addEventListener("keydown", (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && !state.busy) {
        e.preventDefault();
        runOnce();
      }
    });
  }

  async function boot() {
    wire();
    syncSliders();
    try {
      await Promise.all([loadModels(), loadCapabilities()]);
      await restoreSession();
      await Promise.all([loadHistory(), loadStats(), loadSaved()]);
    } catch (err) {
      banner(`<strong>Could not reach the API.</strong> ${escapeHtml(err.message)}`);
    }
  }

  document.addEventListener("DOMContentLoaded", boot);
})();
