async function doLogout() {
  await fetch("/api/auth/logout", { method: "POST" });
  window.location.href = "/login";
}

async function api(path, options = {}) {
  const headers = { ...options.headers };
  if (options.body && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(path, { ...options, headers });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || data.message || "Erro na requisição");
  return data;
}

async function uploadFile(endpoint, file) {
  const form = new FormData();
  form.append("file", file);
  return api(endpoint, { method: "POST", body: form });
}

async function uploadFiles(endpoint, files) {
  const form = new FormData();
  files.forEach(f => form.append("files", f));
  return api(endpoint, { method: "POST", body: form });
}

function toast(msg, type = "success") {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.className = `toast ${type}`;
  setTimeout(() => el.classList.add("hidden"), 4000);
}

function healthBadge(status) {
  const map = {
    healthy: "Conectada",
    warning: "Atenção",
    error: "Erro",
    pending: "Aguardando 2FA",
    unknown: "Sem sessão",
  };
  return `<span class="badge ${status || "unknown"}">${map[status] || status || "—"}</span>`;
}

function setupDropzone(zoneId, inputId, onFiles) {
  const zone = document.getElementById(zoneId);
  const input = document.getElementById(inputId);
  if (!zone || !input) return;

  zone.style.position = "relative";
  zone.style.cursor = "pointer";

  zone.addEventListener("click", (e) => {
    if (e.target === input) return;
    input.click();
  });

  zone.addEventListener("dragover", e => { e.preventDefault(); zone.classList.add("dragover"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
  zone.addEventListener("drop", e => {
    e.preventDefault();
    zone.classList.remove("dragover");
    onFiles([...e.dataTransfer.files]);
  });

  input.addEventListener("change", () => {
    if (input.files?.length) onFiles([...input.files]);
    input.value = "";
  });
}

// --- Dashboard ---

let postsChart = null;
let dashScheduleChart = null;

function scheduleStatusLabel(status) {
  const map = {
    pending: "Pendente",
    processing: "Publicando",
    posted: "Publicado",
    error: "Erro",
    cancelled: "Cancelado",
  };
  return map[status] || status;
}

function formatDateTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

function renderChart(canvasId, config, chartRef) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || typeof Chart === "undefined") return chartRef;
  if (chartRef) chartRef.destroy();
  return new Chart(canvas, config);
}

function sessionLabel(a) {
  if (a.health_status === "healthy") return { text: "Sessão ok", cls: "ok" };
  if (a.health_status === "pending") return { text: "Aguardando 2FA", cls: "warn" };
  if (a.has_session === false || a.health_status === "unknown" || a.health_status === "error") {
    return { text: "Sessão expirada", cls: "bad" };
  }
  if (a.health_status === "warning") return { text: "Atenção", cls: "warn" };
  return { text: a.has_session ? "Sessão ok" : "Sem sessão", cls: a.has_session ? "ok" : "bad" };
}

function topDayBadge(rank) {
  if (rank === 1) return "LENDA";
  if (rank === 2) return "ELITE";
  if (rank <= 4) return "PRO";
  return "NOVO";
}

async function loadDashboard() {
  const grid = document.getElementById("stats-grid");
  if (!grid) return;
  try {
  const days = typeof dashRangeDays === "number" ? dashRangeDays : 7;
  const data = await api(`/api/dashboard?days=${days}`);

  const setText = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  };
  setText("stat-accounts", data.connected_accounts ?? data.total_accounts ?? 0);
  setText("stat-comments", data.comments_answered ?? 0);
  setText("stat-today", data.posts_today ?? 0);
  setText("stat-rate", `${Number(data.success_rate || 0).toFixed(1)}%`);
  const badge = document.getElementById("stat-accounts-badge");
  if (badge) {
    const n = data.total_accounts || 0;
    badge.textContent = n ? `+${n} este mês` : "";
    badge.style.display = n ? "" : "none";
  }

  const storageBanner = document.getElementById("storage-banner");
  if (storageBanner && data.storage) {
    const s = data.storage;
    if (s.recovery?.recovered) {
      storageBanner.className = "notice notice-info";
      storageBanner.innerHTML = `<strong>Dados recuperados do backup SQLite!</strong> ${s.recovery.total_rows} registros restaurados no Postgres.`;
      storageBanner.classList.remove("hidden");
    } else if (s.database_type === "postgresql" && s.database_connected) {
      storageBanner.className = s.accounts_count === 0 ? "notice notice-warning" : "notice notice-info";
      let msg = `<strong>PostgreSQL conectado</strong> (${s.database_host || "Railway"}) — <strong>${s.accounts_count}</strong> conta(s), <strong>${s.post_logs_count || 0}</strong> logs.`;
      if (s.video_files) msg += ` ${s.video_files} vídeo(s) no volume.`;
      else msg += " <strong>Volume /data sem vídeos</strong> — reenvie mídia se necessário.";
      if (s.accounts_count === 0 && s.sqlite_backup?.accounts > 0) {
        msg += ` <button type="button" class="btn secondary" style="margin-left:8px" onclick="runDbRecovery()">Recuperar ${s.sqlite_backup.accounts} conta(s) do backup</button>`;
      }
      storageBanner.innerHTML = msg;
      storageBanner.classList.remove("hidden");
    } else if (s.warning && !s.database_ok) {
      storageBanner.className = "notice notice-warning";
      storageBanner.innerHTML = `<strong>Atenção:</strong> ${s.warning}`;
      storageBanner.classList.remove("hidden");
    } else {
      storageBanner.classList.add("hidden");
    }
  }

  if (data.meta_throttle && !data.meta_throttle.publish_allowed) {
    const banner = document.getElementById("storage-banner") || document.getElementById("global-db-banner");
    if (banner) {
      banner.className = "notice notice-warning";
      const mins = data.meta_throttle.wait_seconds ? Math.ceil(data.meta_throttle.wait_seconds / 60) : 0;
      banner.innerHTML = `<strong>Limite da API Meta (app)</strong> — ${data.meta_throttle.wait_reason || "publicações pausadas temporariamente"}${mins ? ` (~${mins} min)` : ""}.`;
      banner.classList.remove("hidden");
    }
  }

  postsChart = renderChart("posts-chart", {
    type: "line",
    data: {
      labels: data.chart?.labels || [],
      datasets: [
        {
          label: "Publicações",
          data: data.chart?.success || [],
          borderColor: "#e8a838",
          backgroundColor: "rgba(232,168,56,0.18)",
          fill: true,
          tension: 0.35,
          pointRadius: 3,
          pointBackgroundColor: "#e8a838",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: "#c9c2b4", boxWidth: 12 } },
      },
      scales: {
        x: { ticks: { color: "#8f887c" }, grid: { color: "rgba(255,255,255,0.04)" } },
        y: { beginAtZero: true, ticks: { color: "#8f887c", precision: 0 }, grid: { color: "rgba(255,255,255,0.04)" } },
      },
    },
  }, postsChart);

  const autos = document.getElementById("automations-list");
  if (autos) {
    const list = data.automations || [];
    autos.className = list.length ? "auto-list" : "dash-empty";
    autos.innerHTML = list.length
      ? list.map(a => `<div class="auto-item"><span>${a.label}</span><strong>${a.posts} posts</strong></div>`).join("")
      : "Nenhuma automação cadastrada";
  }

  const upcoming = document.getElementById("upcoming-list");
  if (upcoming) {
    const list = data.upcoming || [];
    upcoming.className = list.length ? "upcoming-list" : "dash-empty";
    upcoming.innerHTML = list.length
      ? list.map(u => `
          <div class="upcoming-item">
            <div><strong>${u.account}</strong><div class="meta">${u.media_type}</div></div>
            <span class="meta">${formatDateTime(u.scheduled_at)}</span>
          </div>`).join("")
      : "Nenhuma publicação agendada";
  }

  const activity = document.getElementById("activity-log");
  if (activity) {
    const list = data.activity || [];
    activity.innerHTML = list.length
      ? list.map(p => `
          <div class="activity-item">
            <div class="activity-avatar">${(p.account || "?")[1] || "?"}</div>
            <div class="activity-body">
              <strong>${p.account}</strong>
              <div class="meta">${formatDateTime(p.posted_at)} · ${p.media_type || "REELS"}</div>
            </div>
            <span class="pill ${p.status === "success" ? "ok" : "bad"}">${p.status === "success" ? "Sucesso" : "Erro"}</span>
          </div>`).join("")
      : `<div class="dash-empty">Nenhuma atividade ainda</div>`;
  }

  const insights = document.getElementById("insights-box");
  if (insights) {
    insights.className = "dash-empty";
    insights.innerHTML = "Nenhuma conta via API oficial. Local = Phantom / instagrapi.";
  }

  const top = document.getElementById("top-day");
  if (top) {
    const list = data.top_day || [];
    top.innerHTML = list.length
      ? list.map((t, i) => {
          const rank = i + 1;
          const score = t.posts || t.views || 0;
          return `
            <div class="top-day-item ${rank === 1 ? "first" : ""}">
              <div class="top-day-left">
                <span class="top-day-rank">#${rank}</span>
                <div>
                  <strong>${t.name}</strong>
                  <div class="meta">@${t.username || "—"}</div>
                </div>
              </div>
              <div class="top-day-right">
                <span class="pill gold">${topDayBadge(rank)}</span>
                <strong>${score}</strong>
              </div>
            </div>`;
        }).join("")
      : `<div class="dash-empty">Sem publicações hoje</div>`;
  }

  const connected = document.getElementById("connected-accounts");
  if (connected) {
    const list = (data.accounts || []).slice(0, 8);
    connected.innerHTML = list.length
      ? list.map(a => {
          const s = sessionLabel(a);
          return `
            <div class="connected-item">
              <div>
                <strong>@${a.username || a.name}</strong>
                <div class="meta ${s.cls}">${s.text}</div>
              </div>
              <span class="meta">${a.usage?.posts_last_24h ?? 0} posts</span>
            </div>`;
        }).join("")
      : `<div class="dash-empty">Nenhuma conta. <a href="/accounts" class="dash-link">Conectar</a></div>`;
  }

  const failed = document.getElementById("failed-videos");
  if (failed) {
    const list = data.failed || [];
    failed.className = list.length ? "failed-list" : "dash-empty";
    failed.innerHTML = list.length
      ? list.map(f => `
          <div class="failed-item">
            <div>
              <strong>${f.account}</strong>
              <div class="meta">${formatDateTime(f.posted_at)}</div>
              ${f.error_message ? `<div class="error-detail">${f.error_message}</div>` : ""}
            </div>
            <span class="pill bad">Falha</span>
          </div>`).join("")
      : `Nenhuma falha recente. Veja o <a href="/loop" class="dash-link">Log</a>.`;
  }
  } catch (err) {
    console.error("Dashboard:", err);
    toast(err.message || "Erro ao carregar dashboard", "error");
  }
}

async function refreshAllInsights() {
  const accounts = await api("/api/accounts");
  for (const acc of accounts) {
    await api(`/api/accounts/${acc.id}/insights`).catch(() => null);
    await api(`/api/accounts/${acc.id}/health`).catch(() => null);
  }
  toast("Insights atualizados");
  loadDashboard();
}

function initDashboard() { loadDashboard(); }

// --- Media Library ---

let batchVideoQueue = [];

function formatMb(bytes) {
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

function renderBatchQueue() {
  const queue = document.getElementById("batch-queue");
  const list = document.getElementById("batch-file-list");
  const count = document.getElementById("batch-count");
  if (!queue || !list) return;

  if (!batchVideoQueue.length) {
    queue.classList.add("hidden");
    return;
  }

  queue.classList.remove("hidden");
  if (count) count.textContent = `${batchVideoQueue.length} vídeo(s) na fila`;
  list.innerHTML = batchVideoQueue.map((f, i) => `
    <li>
      <span>${f.name}</span>
      <span class="file-size">${formatMb(f.size)}</span>
      <button type="button" class="btn ghost" style="padding:4px 10px;font-size:0.75rem" onclick="removeFromBatch(${i})">Remover</button>
    </li>
  `).join("");
}

function addVideosToBatch(files) {
  const videos = [...files].filter(f => f.type.startsWith("video/") || /\.(mp4|mov|webm|avi|m4v)$/i.test(f.name));
  if (!videos.length) {
    toast("Nenhum vídeo válido selecionado", "error");
    return;
  }
  batchVideoQueue.push(...videos);
  renderBatchQueue();
  toast(`${videos.length} vídeo(s) adicionado(s) à fila`);
}

function removeFromBatch(index) {
  batchVideoQueue.splice(index, 1);
  renderBatchQueue();
}

function clearBatchQueue() {
  batchVideoQueue = [];
  renderBatchQueue();
}

async function startBatchUpload() {
  if (!batchVideoQueue.length) return;
  const progress = document.getElementById("upload-progress");
  const fill = document.getElementById("progress-fill");
  const text = document.getElementById("progress-text");
  const btn = document.getElementById("batch-start-btn");
  const total = batchVideoQueue.length;
  let ok = 0;
  let fail = 0;

  if (btn) btn.disabled = true;
  if (progress) progress.classList.remove("hidden");

  for (let i = 0; i < total; i++) {
    const file = batchVideoQueue[i];
    const pct = Math.round(((i) / total) * 100);
    if (fill) fill.style.width = pct + "%";
    if (text) text.textContent = `Enviando ${i + 1}/${total}: ${file.name}`;

    try {
      await uploadFile("/api/upload/video", file);
      ok++;
    } catch {
      fail++;
    }
  }

  if (fill) fill.style.width = "100%";
  if (text) text.textContent = `Concluído: ${ok} enviados, ${fail} falhas`;
  toast(`${ok} vídeo(s) enviados em lote${fail ? `, ${fail} falha(s)` : ""}`);

  batchVideoQueue = [];
  renderBatchQueue();
  loadMediaLibrary();

  setTimeout(() => {
    if (progress) progress.classList.add("hidden");
    if (fill) fill.style.width = "0%";
    if (btn) btn.disabled = false;
  }, 3000);
}

async function loadMediaLibrary() {
  const data = await api("/api/uploads");
  const videoGrid = document.getElementById("video-grid");
  const imageGrid = document.getElementById("image-grid");
  const videoCount = document.getElementById("video-count");
  const imageCount = document.getElementById("image-count");

  if (videoCount) videoCount.textContent = data.videos.length;
  if (imageCount) imageCount.textContent = data.images.length;

  if (videoGrid) {
    videoGrid.innerHTML = data.videos.map(v => `
      <div class="media-card">
        <video src="${v.url}" muted preload="metadata"></video>
        <div class="media-card-body">
          <div class="name" title="${v.original_name || v.filename}">${v.original_name || v.filename}</div>
          <div class="hint">${v.size_mb} MB</div>
          <button class="btn secondary" style="margin-top:8px;width:100%" onclick="navigator.clipboard.writeText('${v.url}');toast('URL copiada')">Copiar URL</button>
        </div>
      </div>
    `).join("") || "<p class='hint'>Nenhum vídeo enviado — use o upload em lote acima</p>";
  }

  if (imageGrid) {
    imageGrid.innerHTML = data.images.map(img => `
      <div class="media-card">
        <img src="${img.url}" alt="capa">
        <div class="media-card-body">
          <div class="name">${img.original_name || img.filename}</div>
          <button class="btn secondary" style="margin-top:8px;width:100%" onclick="navigator.clipboard.writeText('${img.url}');toast('URL copiada')">Copiar URL</button>
        </div>
      </div>
    `).join("") || "<p class='hint'>Nenhuma capa enviada</p>";
  }
}

async function handleImageUploads(files) {
  const images = [...files].filter(f => f.type.startsWith("image/"));
  if (!images.length) return toast("Nenhuma imagem válida", "error");

  const progress = document.getElementById("cover-progress");
  if (progress) {
    progress.classList.remove("hidden");
    progress.textContent = `Enviando ${images.length} capa(s)...`;
  }

  let ok = 0;
  for (const f of images) {
    try {
      await uploadFile("/api/upload/image", f);
      ok++;
    } catch { /* continue batch */ }
  }

  toast(`${ok}/${images.length} capa(s) enviada(s)`);
  loadMediaLibrary();
  if (progress) progress.classList.add("hidden");
}

function initMediaPage() {
  setupDropzone("video-dropzone", "video-input", addVideosToBatch);
  setupDropzone("image-dropzone", "image-input", handleImageUploads);
  loadMediaLibrary();
}

// --- Accounts ---

let accountsCache = [];

async function loadAccounts() {
  accountsCache = await api("/api/accounts");
  renderAccountsList();
  populateAccountSelects();
}

function renderAccountsList() {
  const el = document.getElementById("accounts-list");
  if (!el) return;
  const count = document.getElementById("accounts-count");
  if (count) count.textContent = accountsCache.length;

  if (!accountsCache.length) {
    el.innerHTML = `<div class="empty-state">
      <div class="empty-icon">📭</div>
      <p>Nenhuma conta conectada ainda.</p>
      <span class="hint">Preencha o formulário ao lado e clique em <strong>Conectar conta</strong>.</span>
    </div>`;
    return;
  }

  el.innerHTML = accountsCache.map(a => {
    const initial = (a.username || a.name || "?").charAt(0).toUpperCase();
    const connected = a.health_status === "healthy";
    const usage = a.usage.unlimited_day
      ? `${a.usage.posts_last_24h} posts/24h · ∞`
      : `${a.usage.posts_last_24h}/${a.max_posts_per_day} por dia`;
    const connectLabel = connected ? "Reconectar" : "Conectar";
    return `
    <div class="account-card ${a.health_status || "unknown"}">
      <div class="account-avatar">${initial}</div>
      <div class="account-info">
        <div class="account-name">${a.name} ${healthBadge(a.health_status)}</div>
        <div class="account-handle">@${a.username || "sem usuário"}</div>
        <div class="account-meta">
          <span title="Publicações">📊 ${usage}</span>
          <span title="Proxy">${a.proxy_url ? "🛡 Proxy" : "○ Sem proxy"}</span>
        </div>
        ${a.health_message && !connected ? `<div class="account-warn">${a.health_message}</div>` : ""}
      </div>
      <div class="account-actions">
        <button class="btn primary sm" onclick="connectAccount(${a.id})">${connectLabel}</button>
        <button class="btn secondary sm" onclick="editAccount(${a.id})">Editar</button>
        <button class="icon-btn" onclick="deleteAccount(${a.id})" title="Excluir">🗑</button>
      </div>
    </div>`;
  }).join("");
}

function togglePw(inputId, btn) {
  const input = document.getElementById(inputId);
  if (!input) return;
  input.type = input.type === "password" ? "text" : "password";
  if (btn) btn.classList.toggle("on", input.type === "text");
}

function toggleAdvanced() {
  const panel = document.getElementById("advanced-panel");
  const toggle = document.getElementById("advanced-toggle");
  if (!panel) return;
  const open = panel.classList.toggle("open");
  if (toggle) toggle.classList.toggle("open", open);
}

// --- 2FA modal ---
let pendingConnect = null; // { id }

function open2fa(accountId, sub) {
  pendingConnect = { id: accountId };
  const modal = document.getElementById("twofa-modal");
  const subEl = document.getElementById("twofa-sub");
  const code = document.getElementById("twofa-code");
  if (sub && subEl) subEl.textContent = sub;
  if (code) code.value = "";
  if (modal) modal.classList.remove("hidden");
  setTimeout(() => code && code.focus(), 50);
}

function close2fa() {
  pendingConnect = null;
  const modal = document.getElementById("twofa-modal");
  if (modal) modal.classList.add("hidden");
}

async function submit2fa() {
  if (!pendingConnect) return;
  const code = document.getElementById("twofa-code").value.trim();
  if (!code) { toast("Digite o código 2FA", "error"); return; }
  const btn = document.getElementById("twofa-submit");
  if (btn) { btn.disabled = true; btn.textContent = "Conectando..."; }
  try {
    const res = await api(`/api/accounts/${pendingConnect.id}/connect`, {
      method: "POST",
      body: JSON.stringify({ verification_code: code }),
    });
    if (res.login.status === "connected") {
      toast("Conta conectada com sucesso", "success");
      close2fa();
      resetAccountForm();
    } else if (res.login.status === "needs_2fa") {
      toast("Código incorreto, tente novamente", "error");
    } else {
      toast(res.login.message || "Falha ao conectar", "error");
      close2fa();
    }
    loadAccounts();
  } catch (err) {
    toast(err.message, "error");
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "Confirmar e conectar"; }
  }
}

function handleLoginResult(res, { username } = {}) {
  const status = res.login.status;
  if (status === "connected") {
    toast("Conta conectada com sucesso", "success");
    resetAccountForm();
  } else if (status === "needs_2fa") {
    open2fa(res.account.id, `Digite o código 2FA da conta @${username || res.account.username || ""}.`);
  } else {
    toast(res.login.message || "Falha ao conectar a conta", "error");
  }
  loadAccounts();
}

async function connectAccount(id) {
  const a = accountsCache.find(x => x.id === id);
  try {
    const res = await api(`/api/accounts/${id}/connect`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    handleLoginResult(res, { username: a && a.username });
  } catch (err) {
    toast(err.message, "error");
  }
}

function populateAccountSelects() {
  ["post-account", "loop-account", "pub-account", "sch-account", "recurring-account"].forEach(id => {
    const sel = document.getElementById(id);
    if (!sel) return;
    const current = sel.value;
    sel.innerHTML = accountsCache.map(a => `<option value="${a.id}">${a.name}</option>`).join("");
    if (current) sel.value = current;
  });
}

function requireCoverUrl(hiddenId, context) {
  const url = document.getElementById(hiddenId)?.value?.trim();
  if (!url) throw new Error(`Capa obrigatória: faça upload da capa do ${context} antes de continuar`);
  return url;
}

function setCoverPreview(previewId, hiddenId, url) {
  const wrap = document.getElementById(previewId);
  const hidden = document.getElementById(hiddenId);
  if (hidden) hidden.value = url || "";
  if (wrap) {
    wrap.innerHTML = url
      ? `<img src="${url}" alt="Capa do lote">`
      : `<span class="hint">Obrigatória — nenhuma capa</span>`;
  }
}

function bindCoverUpload(inputId, previewId, hiddenId, onDone) {
  const input = document.getElementById(inputId);
  if (!input) return;
  input.addEventListener("change", async () => {
    const file = input.files[0];
    if (!file) return;
    try {
      toast("Enviando capa...");
      const uploaded = await uploadFile("/api/upload/image", file);
      setCoverPreview(previewId, hiddenId, uploaded.url);
      toast("Capa do lote enviada");
      if (onDone) onDone();
    } catch (err) {
      toast(err.message, "error");
    }
    input.value = "";
  });
}

function resetAccountForm() {
  document.getElementById("account-form").reset();
  document.getElementById("account-id").value = "";
  document.getElementById("form-title").textContent = "Conectar nova conta";
  document.getElementById("is_active").checked = true;
  const btn = document.getElementById("connect-btn");
  if (btn) btn.innerHTML = '<span class="btn-icon">🔗</span> Conectar conta';
  const panel = document.getElementById("advanced-panel");
  if (panel) panel.classList.remove("open");
  const toggle = document.getElementById("advanced-toggle");
  if (toggle) toggle.classList.remove("open");
  populateAccountSelects();
}

function editAccount(id) {
  const a = accountsCache.find(x => x.id === id);
  if (!a) return;
  document.getElementById("account-id").value = a.id;
  document.getElementById("form-title").textContent = "Editar conta";
  document.getElementById("name").value = a.name;
  document.getElementById("username").value = a.username || "";
  document.getElementById("password").value = "";
  document.getElementById("sessionid").value = "";
  document.getElementById("proxy_url").value = a.proxy_url || "";
  document.getElementById("max_posts_per_day").value = a.max_posts_per_day;
  document.getElementById("max_posts_per_hour").value = a.max_posts_per_hour;
  document.getElementById("is_active").checked = a.is_active;
  const btn = document.getElementById("connect-btn");
  if (btn) btn.innerHTML = '<span class="btn-icon">💾</span> Salvar alterações';
  const panel = document.getElementById("advanced-panel");
  if (panel) panel.classList.add("open");
  const toggle = document.getElementById("advanced-toggle");
  if (toggle) toggle.classList.add("open");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function saveAccount(e) {
  e.preventDefault();
  const id = document.getElementById("account-id").value;
  const password = document.getElementById("password").value.trim();
  const sessionid = document.getElementById("sessionid").value.trim();
  const username = document.getElementById("username").value.trim();
  const body = {
    name: document.getElementById("name").value,
    username,
    proxy_url: document.getElementById("proxy_url").value,
    max_posts_per_day: +document.getElementById("max_posts_per_day").value,
    max_posts_per_hour: +document.getElementById("max_posts_per_hour").value,
    is_active: document.getElementById("is_active").checked,
  };
  if (password) body.password = password;

  const btn = document.getElementById("connect-btn");
  try {
    if (id) {
      await api(`/api/accounts/${id}`, { method: "PATCH", body: JSON.stringify(body) });
      toast("Conta atualizada", "success");
      resetAccountForm();
      loadAccounts();
      return;
    }
    if (!sessionid && !password) {
      toast("Informe a senha (ou um sessionid em opções avançadas)", "error");
      return;
    }
    if (btn) { btn.disabled = true; btn.innerHTML = "Conectando..."; }
    if (sessionid) body.sessionid = sessionid;
    const res = await api("/api/accounts", { method: "POST", body: JSON.stringify(body) });
    handleLoginResult(res, { username });
  } catch (err) {
    toast(err.message, "error");
  } finally {
    if (btn) { btn.disabled = false; if (!document.getElementById("account-id").value) btn.innerHTML = '<span class="btn-icon">🔗</span> Conectar conta'; }
  }
}

async function deleteAccount(id) {
  if (!confirm("Excluir esta conta?")) return;
  try {
    await api(`/api/accounts/${id}`, { method: "DELETE" });
    toast("Conta excluída");
    if (document.getElementById("account-id")?.value === String(id)) resetAccountForm();
    loadAccounts();
  } catch (err) {
    toast(err.message || "Não foi possível excluir a conta", "error");
  }
}

async function checkHealth(id) {
  const h = await api(`/api/accounts/${id}/health`);
  toast(`Saúde: ${h.status} — ${h.message}`);
  loadAccounts();
}

function initAccountsPage() {
  loadAccounts();
}

// --- Contingency ---

let contingencyCache = [];

async function loadContingencyTable() {
  contingencyCache = await api("/api/contingency");
  const tbody = document.querySelector("#contingency-table tbody");
  if (!tbody) return;

  tbody.innerHTML = contingencyCache.map(a => {
    const options = `<option value="">Nenhuma</option>` + contingencyCache
      .filter(x => x.id !== a.id)
      .map(x => `<option value="${x.id}" ${a.fallback_account_id === x.id ? "selected" : ""}>${x.name}</option>`)
      .join("");
    return `
      <tr>
        <td><strong>${a.name}</strong><br><span class="hint">@${a.username || "—"}</span></td>
        <td>${healthBadge(a.health_status)}</td>
        <td><select class="contingency-select" data-account-id="${a.id}">${options}</select></td>
      </tr>
    `;
  }).join("") || `<tr><td colspan="3" class="hint">Cadastre contas em Contas primeiro</td></tr>`;
}

async function saveContingency() {
  const selects = [...document.querySelectorAll(".contingency-select")];
  const mappings = selects.map(sel => ({
    account_id: +sel.dataset.accountId,
    fallback_account_id: sel.value ? +sel.value : null,
  }));
  try {
    await api("/api/contingency", { method: "PUT", body: JSON.stringify({ mappings }) });
    toast("Mapa de contingência salvo");
    loadContingencyTable();
  } catch (err) {
    toast(err.message, "error");
  }
}

function initContingencyPage() {
  loadContingencyTable();
}

// --- Publish ---

function togglePublishFields() {
  const type = document.getElementById("pub-type").value;
  const uploadBlock = document.getElementById("pub-upload-block");
  const carouselBlock = document.getElementById("pub-carousel-block");
  const coverBlock = document.getElementById("pub-cover-block");
  const audioBlock = document.getElementById("pub-audio-block");
  const captionBlock = document.querySelector(".caption-editor");
  const storyHint = document.getElementById("story-caption-hint");

  if (uploadBlock) uploadBlock.classList.toggle("hidden", type === "carousel");
  if (carouselBlock) carouselBlock.classList.toggle("hidden", type !== "carousel");
  if (coverBlock) coverBlock.classList.toggle("hidden", type !== "reel");
  if (audioBlock) audioBlock.classList.toggle("hidden", type !== "reel");
  if (captionBlock) captionBlock.classList.toggle("hidden", type === "story");
  if (storyHint) storyHint.classList.toggle("hidden", type !== "story");

  const fileInput = document.getElementById("pub-file");
  if (fileInput) {
    fileInput.accept = type === "image" || type === "story"
      ? "video/*,image/jpeg,image/png"
      : "video/*,image/jpeg,image/png";
  }
}

async function publishContent(e) {
  e.preventDefault();
  const accountId = +document.getElementById("pub-account").value;
  const type = document.getElementById("pub-type").value;
  const caption = document.getElementById("pub-caption").value;

  try {
    const file = document.getElementById("pub-file")?.files[0];
    const coverFile = document.getElementById("pub-cover-file")?.files[0];
    let mediaUrl = "";
    let coverUrl = "";

    if (file) {
      toast("Enviando arquivo...");
      const isImage = file.type.startsWith("image/");
      const uploaded = isImage
        ? await uploadFile("/api/upload/image", file)
        : await uploadFile("/api/upload/video", file);
      mediaUrl = uploaded.url;
    }
    if (coverFile) {
      const cover = await uploadFile("/api/upload/image", coverFile);
      coverUrl = cover.url;
    }

    if (type === "story") {
      if (!mediaUrl) throw new Error("Selecione imagem ou vídeo para o Story");
      const isVideo = file?.type.startsWith("video/");
      await api("/api/posts/story", {
        method: "POST",
        body: JSON.stringify({
          account_id: accountId,
          video_url: isVideo ? mediaUrl : "",
          image_url: isVideo ? "" : mediaUrl,
        }),
      });
    } else if (type === "reel") {
      if (!mediaUrl) throw new Error("Selecione um vídeo");
      if (!coverUrl) throw new Error("Capa obrigatória: envie a imagem de capa do Reel");
      await api("/api/posts/reel", {
        method: "POST",
        body: JSON.stringify({
          account_id: accountId,
          video_url: mediaUrl,
          cover_url: coverUrl,
          caption,
          audio_name: document.getElementById("pub-audio-name")?.value || "",
        }),
      });
    } else if (type === "image") {
      if (!mediaUrl) throw new Error("Selecione uma imagem");
      await api("/api/posts/image", {
        method: "POST",
        body: JSON.stringify({ account_id: accountId, image_url: mediaUrl, caption }),
      });
    } else {
      const urls = document.getElementById("pub-carousel-urls").value.split("\n").map(s => s.trim()).filter(Boolean);
      if (urls.length < 2) throw new Error("Carrossel precisa de 2+ URLs");
      await api("/api/posts/carousel", {
        method: "POST",
        body: JSON.stringify({ account_id: accountId, urls, caption }),
      });
    }
    toast("Publicado com sucesso!");
  } catch (err) {
    toast(err.message, "error");
  }
}

function initPublishPage() {
  loadAccounts().then(() => populateAccountSelects());
  togglePublishFields();

  const cap = document.getElementById("pub-caption");
  const counter = document.getElementById("pub-caption-count");
  if (cap && counter) cap.addEventListener("input", () => { counter.textContent = cap.value.length; });

  const pubFile = document.getElementById("pub-file");
  if (pubFile) pubFile.addEventListener("change", () => {
    const lbl = document.getElementById("pub-file-label");
    if (lbl) lbl.textContent = pubFile.files[0]?.name || "Arraste ou clique para selecionar";
  });
  const pubCover = document.getElementById("pub-cover-file");
  if (pubCover) pubCover.addEventListener("change", () => {
    const lbl = document.getElementById("pub-cover-label");
    if (lbl) lbl.textContent = pubCover.files[0]?.name || "Opcional";
  });
}

// --- Loop ---

let videoRowCounter = 0;

function getLoopVideos() {
  return [...document.querySelectorAll("#video-items .video-row")].map(row => ({
    video_url: row.querySelector(".video-url").value.trim(),
    cover_url: row.querySelector(".cover-url").value.trim(),
  })).filter(v => v.video_url);
}

function removeVideoRow(btn, containerId) {
  btn.closest(".video-row")?.remove();
  renumberVideoRows(containerId);
  maybeAutoSaveBatch(containerId);
}

function renumberVideoRows(containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;
  [...container.querySelectorAll(".video-row")].forEach((row, idx) => {
    const title = row.querySelector(".video-row-header strong");
    if (title) title.textContent = `Vídeo #${idx + 1}`;
  });
}

function clearVideoList(containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;
  if (container.children.length && !confirm("Remover todos os vídeos desta lista?")) return;
  container.innerHTML = "";
  if (containerId === "recurring-video-items") saveRecurringBatchSilent(true);
  else saveLoopConfigSilent(true);
}

function addVideoRow(video = {}, containerId = "video-items") {
  const container = document.getElementById(containerId);
  if (!container) return;
  const id = ++videoRowCounter;
  const row = document.createElement("div");
  row.className = "video-row";
  row.dataset.rowId = id;
  row.innerHTML = `
    <div class="video-row-header">
      <strong>Vídeo #${container.children.length + 1}</strong>
      <button type="button" class="btn danger" onclick="removeVideoRow(this, '${containerId}')">Remover</button>
    </div>
    <label class="field-label">URL do vídeo<input class="video-url" value="${video.video_url || ""}" placeholder="Preenchido automaticamente após upload"></label>
    <label class="field-label">URL da capa<input class="cover-url" value="${video.cover_url || ""}" placeholder="Opcional se houver capa do lote"></label>
    <div class="upload-mini">
      <input type="file" class="video-file" accept="video/*" hidden id="vf-${id}">
      <input type="file" class="cover-file" accept="image/*" hidden id="cf-${id}">
      <button type="button" class="btn secondary" onclick="document.getElementById('vf-${id}').click()">Upload vídeo</button>
      <button type="button" class="btn secondary" onclick="document.getElementById('cf-${id}').click()">Upload capa</button>
    </div>
  `;
  container.appendChild(row);

  row.querySelector(".video-file").addEventListener("change", async e => {
    const file = e.target.files[0];
    if (!file) return;
    toast("Enviando vídeo...");
    const uploaded = await uploadFile("/api/upload/video", file);
    row.querySelector(".video-url").value = uploaded.url;
    toast("Vídeo adicionado ao loop");
    maybeAutoSaveBatch(containerId);
  });

  row.querySelector(".cover-file").addEventListener("change", async e => {
    const file = e.target.files[0];
    if (!file) return;
    const uploaded = await uploadFile("/api/upload/image", file);
    row.querySelector(".cover-url").value = uploaded.url;
    toast("Capa adicionada");
    maybeAutoSaveBatch(containerId);
  });
}

async function bulkUploadToLoop(files, containerId = "video-items", replace = true) {
  if (!files.length) return;
  const container = document.getElementById(containerId);
  if (replace && container?.children.length) {
    const label = containerId === "recurring-video-items" ? "lote recorrente" : "loop";
    if (!confirm(`Substituir todos os vídeos do ${label} pelos ${files.length} novo(s)?`)) return;
    container.innerHTML = "";
  }
  toast(`Enviando ${files.length} vídeo(s)...`);
  let ok = 0;
  for (const file of files) {
    try {
      const uploaded = await uploadFile("/api/upload/video", file);
      addVideoRow({ video_url: uploaded.url }, containerId);
      ok++;
    } catch { /* continue */ }
  }
  toast(`${ok} vídeo(s) ${replace ? "substituídos" : "adicionados"}`);
  maybeAutoSaveBatch(containerId);
}

function bulkUploadFromInput(inputId, containerId, replace = false) {
  const input = document.getElementById(inputId);
  if (!input) return;
  const handler = () => {
    if (input.files?.length) bulkUploadToLoop([...input.files], containerId, replace);
    input.value = "";
    input.removeEventListener("change", handler);
  };
  input.addEventListener("change", handler);
  input.click();
}

function formHasFocus(formId) {
  const form = document.getElementById(formId);
  return form && form.contains(document.activeElement);
}

function renderLoopStatus(data) {
  const status = document.getElementById("loop-status");
  if (!status) return;
  status.textContent = [
    `Status: ${data.is_running ? "RODANDO (contínuo)" : "Parado"}`,
    `Índice: ${data.current_index ?? 0}`,
    `Lotes completados: ${data.batches_completed ?? 0}`,
    `Total posts: ${data.total_posts ?? 0}`,
    `Último erro: ${data.last_error || "nenhum"}`,
  ].join("\n");
}

async function refreshLoopStatus() {
  const accountId = document.getElementById("loop-account")?.value;
  if (!accountId) return;
  try {
    const data = await api(`/api/loop/${accountId}`);
    renderLoopStatus(data);
  } catch { /* ignore polling errors */ }
}

async function loadLoopConfig(force = false) {
  const accountId = document.getElementById("loop-account")?.value;
  if (!accountId) return;
  const data = await api(`/api/loop/${accountId}`);
  renderLoopStatus(data);

  if (!force && formHasFocus("loop-form")) return;

  document.getElementById("batch_size").value = data.batch_size;
  document.getElementById("interval_seconds").value = data.interval_seconds;
  document.getElementById("loop-caption").value = data.caption || "";
  const loopCounter = document.getElementById("loop-caption-count");
  if (loopCounter) loopCounter.textContent = (data.caption || "").length;
  setCoverPreview("loop-cover-preview", "loop-cover-url", data.batch_cover_url || "");

  const container = document.getElementById("video-items");
  if (container) {
    container.innerHTML = "";
    (data.videos || []).forEach(v => addVideoRow(v));
  }
}

async function saveLoop(e) {
  if (e?.preventDefault) e.preventDefault();
  const accountId = document.getElementById("loop-account").value;
  const videos = getLoopVideos();

  if (!videos.length) throw new Error("Adicione pelo menos 1 vídeo");

  await api(`/api/loop/${accountId}`, {
    method: "PUT",
    body: JSON.stringify({
      videos,
      caption: document.getElementById("loop-caption").value,
      batch_size: +document.getElementById("batch_size").value,
      interval_seconds: +document.getElementById("interval_seconds").value,
      batch_cover_url: document.getElementById("loop-cover-url")?.value || "",
    }),
  });
  toast("Loop salvo");
  loadLoopConfig(true);
}

async function startLoop() {
  const accountId = document.getElementById("loop-account").value;
  try {
    requireCoverUrl("loop-cover-url", "loop");
    await saveLoop({ preventDefault: () => {} });
    const res = await api(`/api/loop/${accountId}/start`, { method: "POST" });
    toast(res.message);
    loadLoopConfig(true);
  } catch (err) {
    toast(err.message, "error");
  }
}

async function stopLoop() {
  const accountId = document.getElementById("loop-account").value;
  await api(`/api/loop/${accountId}/stop`, { method: "POST" });
  toast("Loop parado");
  loadLoopConfig(true);
}

function setLoopMode(mode) {
  showLoopPanel(mode);
}

function _onLoopPanelSwitch(mode) {
  if (mode === "stagger") {
    setStaggerTarget(staggerTargetMode);
  }
}

// --- Fila escalonada ---

let staggerCandidatesCache = [];
let staggerTargetMode = "loop";

const STAGGER_HINTS = {
  loop: "Configure vídeos + capa na aba <strong>Loop contínuo</strong>. A primeira conta inicia agora; as demais entram na fila.",
  recurring: "Configure vídeos + capa na aba <strong>Lote recorrente</strong>. A primeira conta inicia agora; as demais entram na fila.",
};
const STAGGER_EMPTY = {
  loop: "Nenhuma conta pronta — configure vídeos e capa em Loop contínuo primeiro.",
  recurring: "Nenhuma conta pronta — configure vídeos e capa em Lote recorrente primeiro.",
};

function getStaggerMode() {
  return staggerTargetMode;
}

function setStaggerTarget(mode) {
  staggerTargetMode = mode;
  syncStaggerModeTabs(mode);
  const hint = document.getElementById("stagger-hint");
  if (hint) hint.innerHTML = STAGGER_HINTS[mode] || STAGGER_HINTS.loop;
  if (typeof loadStaggerCandidates === "function") loadStaggerCandidates();
}

function syncStaggerModeTabs(mode) {
  document.querySelectorAll("[data-stagger-mode]").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.staggerMode === mode);
  });
}

async function loadStaggerCandidates() {
  const el = document.getElementById("stagger-candidates");
  if (!el) return;
  const mode = getStaggerMode();
  try {
    staggerCandidatesCache = await api(`/api/loop-stagger/candidates?mode=${mode}`);
    el.innerHTML = staggerCandidatesCache.map(c => `
      <label class="stagger-item ${c.ready ? "" : "disabled"}">
        <input type="checkbox" class="stagger-check" value="${c.account_id}" ${c.ready ? "" : "disabled"}>
        <div>
          <strong>${c.name}</strong>${c.username ? ` @${c.username}` : ""}
          <div class="meta">${c.ready ? `${c.video_count} vídeo(s)${c.is_running ? " · rodando" : ""}` : c.reason}</div>
        </div>
      </label>
    `).join("") || `<p class='hint'>${STAGGER_EMPTY[mode]}</p>`;
    refreshStaggerStatus();
  } catch (err) {
    el.innerHTML = `<p class='hint'>Erro ao carregar: ${err.message}</p>`;
  }
}

function renderStaggerStatus(data) {
  const box = document.getElementById("stagger-active-box");
  if (!box) return;
  if (!data?.active) {
    box.classList.add("hidden");
    return;
  }
  box.classList.remove("hidden");
  const mins = data.wait_seconds ? Math.ceil(data.wait_seconds / 60) : 0;
  const labelPlural = data.label_plural || (data.mode === "recurring" ? "lotes recorrentes" : "loops");
  const list = (data.items || []).map(item => {
    const badge = item.state === "ativo" ? "✓ Ativo"
      : item.state === "proximo" ? "⏳ Próximo"
      : "○ Na fila";
    return `<div><strong>${badge}</strong> ${item.name}${item.username ? ` @${item.username}` : ""}</div>`;
  }).join("");
  box.innerHTML = `
    <strong>Fila em andamento</strong> (${data.mode_label || "loop"}) — ${data.activated_count}/${data.total_count} ${labelPlural} ativos
    ${mins ? ` · próximo em ~${mins} min` : ""}
    <div style="margin-top:10px">${list}</div>
    <div class="meta" style="margin-top:8px">${data.last_message || ""}</div>
  `;
  if (data.mode) {
    staggerTargetMode = data.mode;
    syncStaggerModeTabs(data.mode);
  }
}

async function refreshStaggerStatus() {
  try {
    const data = await api("/api/loop-stagger/status");
    renderStaggerStatus(data);
  } catch { /* ignore */ }
}

async function startStaggerQueue() {
  const ids = [...document.querySelectorAll(".stagger-check:checked")].map(el => +el.value);
  if (!ids.length) {
    toast("Selecione pelo menos 1 conta pronta", "error");
    return;
  }
  const staggerMinutes = +document.getElementById("stagger-minutes")?.value || 15;
  const mode = getStaggerMode();
  try {
    const res = await api("/api/loop-stagger/start", {
      method: "POST",
      body: JSON.stringify({ account_ids: ids, stagger_minutes: staggerMinutes, mode }),
    });
    toast(res.last_message || "Fila escalonada iniciada");
    renderStaggerStatus(res);
    loadStaggerCandidates();
    refreshLoopStatus();
    refreshRecurringStatus();
  } catch (err) {
    toast(err.message, "error");
  }
}

async function stopStaggerQueue() {
  if (!confirm("Cancelar a fila escalonada? Os que já foram ativados continuam rodando.")) return;
  try {
    await api("/api/loop-stagger/stop", { method: "POST" });
    toast("Fila cancelada");
    refreshStaggerStatus();
  } catch (err) {
    toast(err.message, "error");
  }
}

function getRecurringVideos() {
  return [...document.querySelectorAll("#recurring-video-items .video-row")].map(row => ({
    video_url: row.querySelector(".video-url").value.trim(),
    cover_url: row.querySelector(".cover-url").value.trim(),
  })).filter(v => v.video_url);
}

function recurringStatusBadge(data) {
  const map = {
    rodando: { cls: "running", label: "Rodando" },
    aguardando_ciclo: { cls: "waiting", label: "Aguardando próximo ciclo" },
    aguardando_intervalo: { cls: "waiting", label: "Intervalo entre vídeos" },
    limite_api: { cls: "limit", label: "Limite do painel" },
    erro_video: { cls: "limit", label: "Erro no vídeo" },
    parado: { cls: "stopped", label: "Parado" },
  };
  const item = map[data.status_label] || map[data.is_running ? "rodando" : "parado"];
  return `<span class="batch-monitor-badge ${item.cls}">${item.label}</span>`;
}

function formatDurationMinutes(mins) {
  if (mins == null) return "—";
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return h ? `${h}h ${m}min` : `${m}min`;
}

function formatUsageLimit(used, max, unlimited) {
  if (unlimited || max === 0) return `${used} / ∞`;
  return `${used} / ${max}`;
}

function formatUsageRemaining(remaining, max, unlimited) {
  if (unlimited || max === 0) return "ilimitado";
  return `${remaining} restantes`;
}

function formatCountdown(iso) {
  if (!iso) return "—";
  const diff = new Date(iso) - Date.now();
  if (diff <= 0) return "em breve";
  const mins = Math.ceil(diff / 60000);
  return `~${formatDurationMinutes(mins)}`;
}

function renderRecurringActiveList(batches, selectedAccountId) {
  const panel = document.getElementById("recurring-active-panel");
  const list = document.getElementById("recurring-active-list");
  if (!panel || !list) return;

  if (!batches.length) {
    panel.classList.add("hidden");
    list.innerHTML = "";
    return;
  }

  panel.classList.remove("hidden");
  list.innerHTML = batches.map(b => `
    <div class="batch-active-card ${String(b.account_id) === String(selectedAccountId) ? "selected" : ""}"
         onclick="selectRecurringBatch(${b.account_id})">
      <div class="card-top">
        <div>
          <div class="card-title">${b.name || "Lote recorrente"}</div>
          <div class="card-account">${b.account_name}${b.account_username ? ` · @${b.account_username}` : ""}</div>
        </div>
        ${recurringStatusBadge(b)}
      </div>
      <div class="mini-progress"><span style="width:${b.cycle_progress_percent || 0}%"></span></div>
      <div class="card-meta">
        <div><strong>${b.posts_in_current_cycle || 0}/${b.video_count || 0}</strong> vídeos no ciclo</div>
        <div><strong>${b.cycles_completed || 0}</strong> ciclos feitos</div>
        <div><strong>${b.total_posts || 0}</strong> posts totais</div>
        <div><strong>${formatDurationMinutes(b.remaining_minutes)}</strong> restantes</div>
      </div>
    </div>
  `).join("");
}

function renderRecurringStatus(data) {
  const status = document.getElementById("recurring-status");
  if (!status) return;

  if (!data.account_id && !data.is_running && !(data.videos || []).length) {
    status.innerHTML = `<div class="batch-monitor-empty">Configure e inicie o lote recorrente</div>`;
    return;
  }

  const usage = data.usage || {};
  const durationUsed = data.started_at && data.ends_at
    ? Math.max(0, Math.min(100, Math.round(((Date.now() - new Date(data.started_at)) / (new Date(data.ends_at) - new Date(data.started_at))) * 100)))
    : 0;

  let alertHtml = "";
  if (data.last_error) {
    const isLimit = data.last_error.startsWith("Aguardando limite");
    const cls = isLimit ? "warn" : "error";
    alertHtml = `<div class="batch-monitor-alert ${cls}">${data.last_error}</div>`;
  } else if (data.is_running && data.current_video_label) {
    alertHtml = `<div class="batch-monitor-alert info">${data.current_video_label}</div>`;
  }

  status.innerHTML = `
    <div class="batch-monitor-header">
      <div>
        <h3 class="batch-monitor-title">${data.name || "Lote recorrente"}</h3>
        <div class="hint">${data.account_name || "Conta"}${data.account_username ? ` · @${data.account_username}` : ""}</div>
      </div>
      ${recurringStatusBadge(data)}
    </div>
    <div class="batch-monitor-grid">
      <div class="batch-monitor-stat">
        <div class="label">Ciclo atual</div>
        <div class="value">${data.posts_in_current_cycle || 0} / ${data.video_count || 0}</div>
        <div class="sub">vídeos publicados neste lote</div>
      </div>
      <div class="batch-monitor-stat">
        <div class="label">Ciclos completos</div>
        <div class="value">${data.cycles_completed || 0}</div>
        <div class="sub">lotes inteiros finalizados</div>
      </div>
      <div class="batch-monitor-stat">
        <div class="label">Total de posts</div>
        <div class="value">${data.total_posts || 0}</div>
        <div class="sub">desde o início desta execução</div>
      </div>
      <div class="batch-monitor-stat">
        <div class="label">Tempo restante</div>
        <div class="value">${data.is_running ? formatDurationMinutes(data.remaining_minutes) : "—"}</div>
        <div class="sub">${data.ends_at ? `Termina ${formatDateTime(data.ends_at)}` : "Não agendado"}</div>
      </div>
      <div class="batch-monitor-stat">
        <div class="label">Limite / hora (painel)</div>
        <div class="value">${formatUsageLimit(usage.posts_last_hour ?? 0, usage.max_per_hour ?? 0, usage.unlimited_hour)}</div>
        <div class="sub">${formatUsageRemaining(usage.remaining_hour, usage.max_per_hour, usage.unlimited_hour)} na hora</div>
      </div>
      <div class="batch-monitor-stat">
        <div class="label">Limite / dia (painel)</div>
        <div class="value">${formatUsageLimit(usage.posts_last_24h ?? 0, usage.max_per_day ?? 0, usage.unlimited_day)}</div>
        <div class="sub">${formatUsageRemaining(usage.remaining_day, usage.max_per_day, usage.unlimited_day)} no dia</div>
      </div>
    </div>
    <div class="batch-monitor-progress">
      <div class="progress-label">
        <span>Progresso do ciclo atual</span>
        <strong>${data.cycle_progress_percent || 0}%</strong>
      </div>
      <div class="batch-progress-bar"><span style="width:${data.cycle_progress_percent || 0}%"></span></div>
    </div>
    <div class="batch-monitor-progress">
      <div class="progress-label">
        <span>Duração total da execução</span>
        <strong>${durationUsed}% · ${data.duration_hours || 0}h configuradas</strong>
      </div>
      <div class="batch-progress-bar"><span style="width:${durationUsed}%"></span></div>
    </div>
    <div class="batch-monitor-footer">
      <div class="batch-monitor-row">
        <span><strong>Intervalo entre lotes:</strong> ${data.cycle_interval_hours || 1}h</span>
        <span><strong>Intervalo entre vídeos:</strong> ${data.video_interval_seconds || 0}s</span>
        <span><strong>Próximo vídeo:</strong> ${data.waiting_for_video ? formatCountdown(data.next_post_at || data.next_retry_at) : (data.is_running ? "pronto" : "—")}</span>
        <span><strong>Próximo ciclo:</strong> ${data.waiting_for_cycle ? formatCountdown(data.next_cycle_at) : (data.is_running ? "após completar o lote" : "—")}</span>
        ${data.consecutive_failures ? `<span><strong>Tentativas falhas:</strong> ${data.consecutive_failures}/3 no vídeo atual</span>` : ""}
      </div>
      ${alertHtml}
    </div>
  `;
}

async function loadRecurringActiveBatches() {
  try {
    const batches = await api("/api/recurring-batches/active");
    const accountId = document.getElementById("recurring-account")?.value
      || document.getElementById("loop-account")?.value;
    renderRecurringActiveList(batches, accountId);
  } catch { /* ignore */ }
}

function selectRecurringBatch(accountId) {
  const recurringSel = document.getElementById("recurring-account");
  const loopSel = document.getElementById("loop-account");
  if (recurringSel) recurringSel.value = accountId;
  if (loopSel) loopSel.value = accountId;
  setLoopMode("recurring");
  loadRecurringConfig(true);
  loadRecurringActiveBatches();
}

async function refreshRecurringStatus() {
  const accountId = document.getElementById("recurring-account")?.value
    || document.getElementById("loop-account")?.value;
  if (!accountId) return;
  try {
    const data = await api(`/api/recurring-batch/${accountId}`);
    renderRecurringStatus(data);
    loadRecurringActiveBatches();
  } catch { /* ignore polling errors */ }
}

async function loadRecurringConfig(force = false) {
  const accountId = document.getElementById("recurring-account")?.value
    || document.getElementById("loop-account")?.value;
  if (!accountId) return;

  const recurringSel = document.getElementById("recurring-account");
  const loopSel = document.getElementById("loop-account");
  if (recurringSel && loopSel && recurringSel.value !== loopSel.value) {
    recurringSel.value = loopSel.value;
  }

  const data = await api(`/api/recurring-batch/${accountId}`);
  renderRecurringStatus(data);
  loadRecurringActiveBatches();

  if (!force && formHasFocus("recurring-form")) return;

  document.getElementById("recurring-name").value = data.name || "Lote recorrente";
  document.getElementById("recurring-duration").value = String(data.duration_hours || 12);
  document.getElementById("recurring-cycle-hours").value = data.cycle_interval_hours || 1;
  document.getElementById("recurring-video-interval").value = data.video_interval_seconds || 60;
  document.getElementById("recurring-caption").value = data.caption || "";
  const recCounter = document.getElementById("recurring-caption-count");
  if (recCounter) recCounter.textContent = (data.caption || "").length;
  setCoverPreview("recurring-cover-preview", "recurring-cover-url", data.cover_url || "");
  document.getElementById("recurring-hint-hours").textContent = data.cycle_interval_hours || 1;

  const container = document.getElementById("recurring-video-items");
  if (container) {
    container.innerHTML = "";
    (data.videos || []).forEach(v => addVideoRow(v, "recurring-video-items"));
  }
}

function maybeAutoSaveBatch(containerId) {
  if (containerId === "recurring-video-items") saveRecurringBatchSilent();
  if (containerId === "video-items") saveLoopConfigSilent();
}

async function saveRecurringBatchSilent(allowEmpty = false) {
  const accountId = document.getElementById("recurring-account")?.value
    || document.getElementById("loop-account")?.value;
  if (!accountId) return;
  const videos = getRecurringVideos();
  if (!videos.length && !allowEmpty) return;
  try {
    await api(`/api/recurring-batch/${accountId}`, {
      method: "PUT",
      body: JSON.stringify({
        name: document.getElementById("recurring-name").value,
        videos,
        caption: document.getElementById("recurring-caption").value,
        cover_url: document.getElementById("recurring-cover-url")?.value || "",
        duration_hours: +document.getElementById("recurring-duration").value,
        cycle_interval_hours: +document.getElementById("recurring-cycle-hours").value,
        video_interval_seconds: +document.getElementById("recurring-video-interval").value,
      }),
    });
  } catch { /* auto-save silencioso */ }
}

async function saveLoopConfigSilent(allowEmpty = false) {
  const accountId = document.getElementById("loop-account")?.value;
  if (!accountId) return;
  const videos = getLoopVideos();
  if (!videos.length && !allowEmpty) return;
  try {
    await api(`/api/loop/${accountId}`, {
      method: "PUT",
      body: JSON.stringify({
        videos,
        caption: document.getElementById("loop-caption").value,
        batch_size: +document.getElementById("batch_size").value,
        interval_seconds: +document.getElementById("interval_seconds").value,
        batch_cover_url: document.getElementById("loop-cover-url")?.value || "",
      }),
    });
  } catch { /* auto-save silencioso */ }
}

async function saveRecurringBatch(e) {
  if (e?.preventDefault) e.preventDefault();
  const accountId = document.getElementById("recurring-account").value
    || document.getElementById("loop-account").value;
  const videos = getRecurringVideos();
  if (!videos.length) throw new Error("Adicione pelo menos 1 vídeo ao lote");

  await api(`/api/recurring-batch/${accountId}`, {
    method: "PUT",
    body: JSON.stringify({
      name: document.getElementById("recurring-name").value,
      videos,
      caption: document.getElementById("recurring-caption").value,
      cover_url: document.getElementById("recurring-cover-url")?.value || "",
      duration_hours: +document.getElementById("recurring-duration").value,
      cycle_interval_hours: +document.getElementById("recurring-cycle-hours").value,
      video_interval_seconds: +document.getElementById("recurring-video-interval").value,
    }),
  });
  toast("Lote recorrente salvo");
  loadRecurringConfig(true);
}

async function startRecurringBatch() {
  const accountId = document.getElementById("recurring-account").value
    || document.getElementById("loop-account").value;
  try {
    requireCoverUrl("recurring-cover-url", "lote recorrente");
    await saveRecurringBatch({ preventDefault: () => {} });
    const duration = +document.getElementById("recurring-duration").value;
    const res = await api(`/api/recurring-batch/${accountId}/start`, {
      method: "POST",
      body: JSON.stringify({ duration_hours: duration }),
    });
    toast(res.message);
    loadRecurringConfig(true);
    loadLoopConfig(true);
  } catch (err) {
    toast(err.message, "error");
  }
}

async function stopRecurringBatch() {
  const accountId = document.getElementById("recurring-account").value
    || document.getElementById("loop-account").value;
  await api(`/api/recurring-batch/${accountId}/stop`, { method: "POST" });
  toast("Lote recorrente parado");
  loadRecurringConfig(true);
}

async function initLoopPage() {
  await loadAccounts();
  populateAccountSelects();

  setupDropzone("loop-video-dropzone", "loop-bulk-upload", files => bulkUploadToLoop(files, "video-items", true));
  setupDropzone("recurring-dropzone", "recurring-upload", files => bulkUploadToLoop(files, "recurring-video-items", true));

  bindCoverUpload("loop-cover-input", "loop-cover-preview", "loop-cover-url", () => saveLoopConfigSilent());
  bindCoverUpload("recurring-cover-input", "recurring-cover-preview", "recurring-cover-url", () => saveRecurringBatchSilent());

  const loopCap = document.getElementById("loop-caption");
  const loopCounter = document.getElementById("loop-caption-count");
  if (loopCap && loopCounter) {
    loopCap.addEventListener("input", () => { loopCounter.textContent = loopCap.value.length; });
  }

  const recCap = document.getElementById("recurring-caption");
  const recCounter = document.getElementById("recurring-caption-count");
  if (recCap && recCounter) {
    recCap.addEventListener("input", () => { recCounter.textContent = recCap.value.length; });
  }

  document.getElementById("recurring-cycle-hours")?.addEventListener("input", e => {
    const hint = document.getElementById("recurring-hint-hours");
    if (hint) hint.textContent = e.target.value;
  });

  document.getElementById("loop-account")?.addEventListener("change", () => {
    const rec = document.getElementById("recurring-account");
    if (rec) rec.value = document.getElementById("loop-account").value;
    loadLoopConfig(true);
    loadRecurringConfig(true);
  });

  document.getElementById("recurring-account")?.addEventListener("change", () => {
    const loop = document.getElementById("loop-account");
    if (loop) loop.value = document.getElementById("recurring-account").value;
    loadRecurringConfig(true);
    loadLoopConfig(true);
  });

  loadLoopConfig(true);
  loadRecurringConfig(true);
  loadStaggerCandidates();
}

// --- Schedule ---

let scheduleListChart = null;
let scheduleBatch = [];

function getScheduleStartDate() {
  const val = document.getElementById("sch-start")?.value;
  if (!val) return new Date();
  return new Date(val);
}

function computeScheduledTime(index) {
  const start = getScheduleStartDate();
  const interval = +(document.getElementById("sch-interval")?.value || 60);
  return new Date(start.getTime() + interval * index * 60000);
}

function renderSchedulePreview() {
  const grid = document.getElementById("sch-preview-grid");
  const countEl = document.getElementById("sch-batch-count");
  const submitBtn = document.getElementById("sch-submit-btn");
  if (!grid) return;

  if (countEl) countEl.textContent = scheduleBatch.length;
  if (submitBtn) submitBtn.disabled = !scheduleBatch.length;

  if (!scheduleBatch.length) {
    grid.innerHTML = "<p class='hint'>Nenhum vídeo — arraste arquivos no upload acima</p>";
    return;
  }

  const coverUrl = document.getElementById("sch-cover-url")?.value || "";
  grid.innerHTML = scheduleBatch.map((item, i) => `
    <div class="preview-card">
      <div class="thumb-overlay">
        <video src="${item.video_url}" muted preload="metadata"></video>
        ${coverUrl ? `<img class="cover-thumb" src="${coverUrl}" alt="capa">` : ""}
      </div>
      <div class="preview-card-body">
        <div class="name" title="${item.name}">${item.name}</div>
        <div class="time">${formatDateTime(computeScheduledTime(i).toISOString())}</div>
        <button type="button" class="btn ghost" style="margin-top:6px;width:100%;padding:4px;font-size:0.7rem" onclick="removeScheduleBatchItem(${i})">Remover</button>
      </div>
    </div>
  `).join("");
}

function removeScheduleBatchItem(index) {
  scheduleBatch.splice(index, 1);
  renderSchedulePreview();
}

function clearScheduleBatch() {
  scheduleBatch = [];
  renderSchedulePreview();
}

async function uploadVideosToBatch(files) {
  const videos = [...files].filter(f =>
    f.type.startsWith("video/") || /\.(mp4|mov|webm|avi|m4v)$/i.test(f.name)
  );
  if (!videos.length) return toast("Nenhum vídeo válido", "error");

  const progress = document.getElementById("sch-upload-progress");
  const fill = document.getElementById("sch-progress-fill");
  const text = document.getElementById("sch-progress-text");
  if (progress) progress.classList.remove("hidden");

  let ok = 0;
  for (let i = 0; i < videos.length; i++) {
    const file = videos[i];
    const pct = Math.round((i / videos.length) * 100);
    if (fill) fill.style.width = pct + "%";
    if (text) text.textContent = `Enviando ${i + 1}/${videos.length}: ${file.name}`;

    try {
      const uploaded = await uploadFile("/api/upload/video", file);
      scheduleBatch.push({
        video_url: uploaded.url,
        cover_url: "",
        name: file.name,
      });
      ok++;
      renderSchedulePreview();
    } catch { /* continue */ }
  }

  if (fill) fill.style.width = "100%";
  if (text) text.textContent = `Concluído: ${ok}/${videos.length} vídeos prontos para agendar`;
  toast(`${ok} vídeo(s) enviado(s) — URLs geradas automaticamente`);

  setTimeout(() => {
    if (progress) progress.classList.add("hidden");
    if (fill) fill.style.width = "0%";
  }, 2500);
}

function toIsoLocal(dtLocal) {
  if (!dtLocal) return "";
  return new Date(dtLocal).toISOString();
}

async function submitSchedule(e) {
  e.preventDefault();
  if (!scheduleBatch.length) return toast("Envie pelo menos 1 vídeo", "error");

  try {
    requireCoverUrl("sch-cover-url", "agendamento");
  } catch (err) {
    return toast(err.message, "error");
  }

  const accountId = +document.getElementById("sch-account").value;
  const body = {
    name: document.getElementById("sch-name").value,
    account_id: accountId,
    cover_url: document.getElementById("sch-cover-url")?.value || "",
    start_at: toIsoLocal(document.getElementById("sch-start").value),
    interval_minutes: +document.getElementById("sch-interval").value,
    caption: document.getElementById("sch-caption").value,
    videos: scheduleBatch.map(v => ({ video_url: v.video_url, cover_url: v.cover_url || "" })),
  };

  try {
    const res = await api("/api/schedule/batch", { method: "POST", body: JSON.stringify(body) });
    toast(`${res.created} Reel(s) agendado(s) com sucesso`);
    scheduleBatch = [];
    renderSchedulePreview();
    loadScheduleList();
  } catch (err) {
    toast(err.message, "error");
  }
}

async function cancelSchedule(id) {
  if (!confirm("Cancelar este agendamento?")) return;
  try {
    await api(`/api/schedule/${id}`, { method: "DELETE" });
    toast("Agendamento cancelado");
    loadScheduleList();
  } catch (err) {
    toast(err.message, "error");
  }
}

async function loadScheduleList() {
  const list = document.getElementById("schedule-list");
  const statsEl = document.getElementById("schedule-stats");
  if (!list && !statsEl) return;

  const items = await api("/api/schedule");
  const stats = { pending: 0, posted: 0, error: 0, processing: 0, cancelled: 0 };
  items.forEach(i => { stats[i.status] = (stats[i.status] || 0) + 1; });

  if (statsEl) {
    statsEl.innerHTML = `
      <div class="stat-card"><div class="value">${stats.pending || 0}</div><div class="label">Pendentes</div></div>
      <div class="stat-card"><div class="value">${stats.posted || 0}</div><div class="label">Publicados</div></div>
      <div class="stat-card"><div class="value">${stats.error || 0}</div><div class="label">Erros</div></div>
      <div class="stat-card"><div class="value">${stats.processing || 0}</div><div class="label">Processando</div></div>
    `;
  }

  if (document.getElementById("schedule-chart")) {
    scheduleListChart = renderChart("schedule-chart", {
      type: "doughnut",
      data: {
        labels: ["Pendentes", "Publicados", "Erros", "Processando"],
        datasets: [{
          data: [stats.pending || 0, stats.posted || 0, stats.error || 0, stats.processing || 0],
          backgroundColor: ["#60a5fa", "#4ade80", "#f87171", "#fbbf24"],
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: "bottom", labels: { color: "#cbd5e1" } } },
      },
    }, scheduleListChart);
  }

  if (list) {
    list.innerHTML = items.length ? items.map(i => `
      <div class="schedule-item">
        <video src="${i.video_url}" muted preload="metadata"></video>
        <div>
          <strong>${i.account_name}</strong>
          ${i.posted_account_name && i.posted_account_name !== i.account_name ? `<span class="hint"> → ${i.posted_account_name} (contingência)</span>` : ""}
          <div class="meta">${formatDateTime(i.scheduled_at)}${i.posted_at ? ` · publicado ${formatDateTime(i.posted_at)}` : ""}</div>
          <div class="meta">${i.caption ? i.caption.slice(0, 80) : "Sem legenda"}</div>
          ${i.error_message ? `<div class="error-text">${i.error_message}</div>` : ""}
        </div>
        <div style="text-align:right">
          <span class="status-badge ${i.status}">${scheduleStatusLabel(i.status)}</span>
          ${i.status === "pending" || i.status === "error" ? `<div style="margin-top:8px"><button class="btn ghost" style="font-size:0.75rem" onclick="cancelSchedule(${i.id})">Cancelar</button></div>` : ""}
        </div>
      </div>
    `).join("") : "<p class='hint'>Nenhum agendamento ainda — envie vídeos e clique em Agendar lote</p>";
  }
}

async function initSchedulePage() {
  await loadAccounts();
  populateAccountSelects();

  const cap = document.getElementById("sch-caption");
  const counter = document.getElementById("sch-caption-count");
  if (cap && counter) cap.addEventListener("input", () => { counter.textContent = cap.value.length; });

  bindCoverUpload("sch-cover-input", "sch-cover-preview", "sch-cover-url", renderSchedulePreview);

  const start = document.getElementById("sch-start");
  if (start) {
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    start.value = now.toISOString().slice(0, 16);
    start.addEventListener("change", renderSchedulePreview);
  }

  document.getElementById("sch-interval")?.addEventListener("input", renderSchedulePreview);

  setupDropzone("sch-dropzone", "sch-file-input", uploadVideosToBatch);

  renderSchedulePreview();
  loadScheduleList();
  setInterval(loadScheduleList, 15000);
}

// --- Settings ---

async function initSettingsPage() {
  try {
    const me = await api("/api/me");
    if (me.role !== "owner") {
      window.location.href = "/";
      return;
    }
  } catch {
    window.location.href = "/login";
    return;
  }
  const data = await api("/api/settings");
  document.getElementById("default_max_posts_per_day").value = data.default_max_posts_per_day;
  document.getElementById("default_max_posts_per_hour").value = data.default_max_posts_per_hour;
  document.getElementById("default_loop_batch_size").value = data.default_loop_batch_size;
  document.getElementById("default_loop_interval_seconds").value = data.default_loop_interval_seconds;
  document.getElementById("current-accounts").textContent = data.current_accounts;
}

async function initUsersPage() {
  try {
    const me = await api("/api/me");
    if (me.role !== "owner") {
      document.getElementById("nav-users")?.classList.add("hidden");
      window.location.href = "/";
      return;
    }
    loadUsersList();
  } catch {
    window.location.href = "/login";
  }
}

async function loadUsersList() {
  const users = await api("/api/users");
  const el = document.getElementById("users-list");
  if (!el) return;
  el.innerHTML = users.map(u => `
    <div class="account-item">
      <div>
        <strong>${u.username}</strong>
        <div class="meta">${u.role === "owner" ? "Proprietário" : "Cliente"} | ${u.is_active ? "Ativo" : "Inativo"}</div>
      </div>
      ${u.role !== "owner" ? `<button class="btn danger" onclick="deletePanelUser(${u.id})">Excluir</button>` : ""}
    </div>
  `).join("") || "<p class='hint'>Nenhum usuário</p>";
}

async function createPanelUser(e) {
  e.preventDefault();
  try {
    await api("/api/users", {
      method: "POST",
      body: JSON.stringify({
        username: document.getElementById("new-username").value,
        password: document.getElementById("new-password").value,
      }),
    });
    toast("Usuário criado");
    document.getElementById("user-form").reset();
    loadUsersList();
  } catch (err) {
    toast(err.message, "error");
  }
}

async function deletePanelUser(id) {
  if (!confirm("Excluir este usuário?")) return;
  await api(`/api/users/${id}`, { method: "DELETE" });
  toast("Usuário excluído");
  loadUsersList();
}

document.addEventListener("DOMContentLoaded", () => {
  api("/api/me").then(me => {
    if (me.role !== "owner") {
      document.getElementById("nav-users")?.classList.add("hidden");
      document.getElementById("nav-settings")?.classList.add("hidden");
    }
  }).catch(() => {});
});

async function saveSettings(e) {
  e.preventDefault();
  try {
    await api("/api/settings", {
      method: "PUT",
      body: JSON.stringify({
        default_max_posts_per_day: +document.getElementById("default_max_posts_per_day").value,
        default_max_posts_per_hour: +document.getElementById("default_max_posts_per_hour").value,
        default_loop_batch_size: +document.getElementById("default_loop_batch_size").value,
        default_loop_interval_seconds: +document.getElementById("default_loop_interval_seconds").value,
      }),
    });
    toast("Configurações salvas");
  } catch (err) {
    toast(err.message, "error");
  }
}

async function runDbRecovery() {
  if (!confirm("Recuperar contas, loops e logs do backup SQLite no volume /data?")) return;
  try {
    const res = await api("/api/recovery/sqlite", { method: "POST" });
    toast(`Recuperado: ${res.total_rows} registros`);
    location.reload();
  } catch (err) {
    toast(err.message || "Falha na recuperação", "error");
  }
}

async function loadGlobalDbBanner() {
  const el = document.getElementById("global-db-banner");
  if (!el) return;
  try {
    const data = await api("/api/storage");
    if (data.recovery?.recovered) {
      el.className = "notice notice-info";
      el.innerHTML = `<strong>Dados recuperados!</strong> ${data.recovery.total_rows} registros restaurados do backup SQLite.`;
      el.classList.remove("hidden");
      return;
    }
    if (data.warning) {
      el.className = "notice notice-warning";
      let html = `<strong>Atenção:</strong> ${data.warning}`;
      if (data.sqlite_backup?.accounts > 0 && data.accounts_count === 0) {
        html += ` <button type="button" class="btn secondary" style="margin-left:8px" onclick="runDbRecovery()">Recuperar agora</button>`;
      }
      el.innerHTML = html;
      el.classList.remove("hidden");
      return;
    }
    if (data.database_connected && data.accounts_count === 0) {
      el.className = "notice notice-warning";
      el.innerHTML = `<strong>Painel vazio:</strong> 0 contas no ${data.database_type}. Se tinha dados antes, o volume Postgres pode ter sido recriado na Railway.`;
      el.classList.remove("hidden");
    }
  } catch { /* login page */ }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", loadGlobalDbBanner);
} else {
  loadGlobalDbBanner();
}
