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
  const map = { healthy: "Saudável", warning: "Atenção", error: "Erro", unknown: "?" };
  return `<span class="badge ${status}">${map[status] || status}</span>`;
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

async function loadDashboard() {
  const data = await api("/api/dashboard");
  const grid = document.getElementById("stats-grid");
  if (!grid) return;

  grid.innerHTML = `
    <div class="stat-card"><div class="value">${data.total_accounts}</div><div class="label">Contas</div></div>
    <div class="stat-card"><div class="value">${data.total_posts}</div><div class="label">Posts publicados</div></div>
    <div class="stat-card"><div class="value">${data.total_errors}</div><div class="label">Erros</div></div>
    <div class="stat-card"><div class="value">${data.running_loops}</div><div class="label">Loops ativos</div></div>
    <div class="stat-card"><div class="value">${data.running_recurring || 0}</div><div class="label">Lotes recorrentes</div></div>
    <div class="stat-card"><div class="value">${data.pending_schedule || 0}</div><div class="label">Agendados</div></div>
  `;

  const storageBanner = document.getElementById("storage-banner");
  if (storageBanner && data.storage) {
    const s = data.storage;
    if (s.database_type === "postgresql" && s.database_connected) {
      storageBanner.className = "notice notice-info";
      storageBanner.innerHTML = `<strong>PostgreSQL conectado</strong> (${s.database_host || "Railway"}) — contas, agendamentos e logs persistem no banco.${s.persistent_volume ? ` Vídeos em <code>${s.data_dir}</code>.` : " <strong>Monte volume /data</strong> no serviço postagemIG para não perder vídeos."}`;
      storageBanner.classList.remove("hidden");
    } else if (s.persistent_volume && s.writable && s.database_ok) {
      storageBanner.className = "notice notice-info";
      storageBanner.innerHTML = `<strong>Armazenamento persistente:</strong> volume ativo em <code>${s.data_dir}</code> — dados mantidos nos redeploys.`;
      storageBanner.classList.remove("hidden");
    } else {
      storageBanner.className = "notice notice-warning";
      storageBanner.innerHTML = `<strong>Atenção:</strong> ${s.warning || "Configure Postgres (DATABASE_URL) e volume /data na Railway."}`;
      storageBanner.classList.remove("hidden");
    }
  }

  postsChart = renderChart("posts-chart", {
    type: "bar",
    data: {
      labels: data.chart?.labels || [],
      datasets: [
        {
          label: "Sucesso",
          data: data.chart?.success || [],
          backgroundColor: "rgba(34,197,94,0.7)",
          borderRadius: 6,
        },
        {
          label: "Erros",
          data: data.chart?.errors || [],
          backgroundColor: "rgba(239,68,68,0.7)",
          borderRadius: 6,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: "#cbd5e1" } } },
      scales: {
        x: { ticks: { color: "#94a3b8" }, grid: { color: "rgba(255,255,255,0.05)" } },
        y: { beginAtZero: true, ticks: { color: "#94a3b8", precision: 0 }, grid: { color: "rgba(255,255,255,0.05)" } },
      },
    },
  }, postsChart);

  const ss = data.schedule_stats || {};
  dashScheduleChart = renderChart("schedule-chart", {
    type: "doughnut",
    data: {
      labels: ["Pendentes", "Publicados", "Erros", "Processando"],
      datasets: [{
        data: [ss.pending || 0, ss.posted || 0, ss.error || 0, ss.processing || 0],
        backgroundColor: ["#60a5fa", "#4ade80", "#f87171", "#fbbf24"],
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: "bottom", labels: { color: "#cbd5e1" } } },
    },
  }, dashScheduleChart);

  const tbody = document.querySelector("#accounts-table tbody");
  if (tbody) {
    tbody.innerHTML = data.accounts.map(a => {
      const fallback = a.fallback_account_id
        ? data.accounts.find(x => x.id === a.fallback_account_id)?.name || `#${a.fallback_account_id}`
        : "—";
      return `
      <tr>
        <td><strong>${a.name}</strong><br><span class="hint">@${a.username || "—"}</span></td>
        <td>${healthBadge(a.health_status)}</td>
        <td>${a.profile_views.toLocaleString()}</td>
        <td>${a.total_reach.toLocaleString()}</td>
        <td>${a.usage.posts_last_24h}/${a.max_posts_per_day}</td>
        <td>${a.loop_running ? '<span class="badge running">Ativo</span>' : "Parado"} (${a.loop_posts})</td>
        <td>${fallback}</td>
        <td>${a.proxy_url ? "✓" : "—"}</td>
      </tr>
    `}).join("");
  }

  const recent = document.getElementById("recent-posts");
  if (recent) {
    const posts = await api("/api/recent-posts");
    recent.innerHTML = posts.length ? posts.map(p => `
      <div class="post-log-item">
        <div>
          <strong>${p.account}</strong> @${p.username || "—"} — ${p.media_type}
          <div class="meta">${formatDateTime(p.posted_at)}</div>
          ${p.caption_preview ? `<div class="meta">${p.caption_preview}</div>` : ""}
          ${p.status === "error" && p.error_message ? `<div class="error-detail">${p.error_message}</div>` : ""}
        </div>
        <span class="status-badge ${p.status === "success" ? "posted" : p.status}">${p.status === "success" ? "OK" : "Erro"}</span>
      </div>
    `).join("") : "<p class='hint'>Nenhuma publicação ainda — publique em Publicar, inicie um Loop ou agende vídeos</p>";
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
  el.innerHTML = accountsCache.map(a => `
    <div class="account-item">
      <div>
        <strong>${a.name}</strong> @${a.username || "—"}
        <div class="meta">${healthBadge(a.health_status)} | ${a.usage.posts_last_24h}/${a.max_posts_per_day}d | Proxy: ${a.proxy_url ? "sim" : "não"}</div>
      </div>
      <div class="actions">
        <button class="btn secondary" onclick="editAccount(${a.id})">Editar</button>
        <button class="btn secondary" onclick="checkHealth(${a.id})">Saúde</button>
        <button class="btn danger" onclick="deleteAccount(${a.id})">Excluir</button>
      </div>
    </div>
  `).join("") || "<p class='hint'>Nenhuma conta cadastrada</p>";
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

function setCoverPreview(previewId, hiddenId, url) {
  const wrap = document.getElementById(previewId);
  const hidden = document.getElementById(hiddenId);
  if (hidden) hidden.value = url || "";
  if (wrap) {
    wrap.innerHTML = url
      ? `<img src="${url}" alt="Capa do lote">`
      : `<span class="hint">Nenhuma capa</span>`;
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
  document.getElementById("form-title").textContent = "Nova conta";
  document.getElementById("is_active").checked = true;
  populateAccountSelects();
}

function editAccount(id) {
  const a = accountsCache.find(x => x.id === id);
  if (!a) return;
  document.getElementById("account-id").value = a.id;
  document.getElementById("form-title").textContent = "Editar conta";
  document.getElementById("name").value = a.name;
  document.getElementById("ig_user_id").value = a.ig_user_id;
  document.getElementById("access_token").value = "••••••••";
  document.getElementById("proxy_url").value = a.proxy_url || "";
  document.getElementById("username").value = a.username || "";
  document.getElementById("max_posts_per_day").value = a.max_posts_per_day;
  document.getElementById("max_posts_per_hour").value = a.max_posts_per_hour;
  document.getElementById("is_active").checked = a.is_active;
}

async function saveAccount(e) {
  e.preventDefault();
  const id = document.getElementById("account-id").value;
  const token = document.getElementById("access_token").value;
  const body = {
    name: document.getElementById("name").value,
    ig_user_id: document.getElementById("ig_user_id").value,
    proxy_url: document.getElementById("proxy_url").value,
    username: document.getElementById("username").value,
    max_posts_per_day: +document.getElementById("max_posts_per_day").value,
    max_posts_per_hour: +document.getElementById("max_posts_per_hour").value,
    is_active: document.getElementById("is_active").checked,
  };
  if (token && token !== "••••••••") body.access_token = token;
  try {
    if (id) {
      await api(`/api/accounts/${id}`, { method: "PATCH", body: JSON.stringify(body) });
      toast("Conta atualizada");
    } else {
      body.access_token = token;
      await api("/api/accounts", { method: "POST", body: JSON.stringify(body) });
      toast("Conta criada");
    }
    resetAccountForm();
    loadAccounts();
  } catch (err) {
    toast(err.message, "error");
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
      <button type="button" class="btn danger" onclick="this.closest('.video-row').remove()">Remover</button>
    </div>
    <label class="field-label">URL do vídeo<input class="video-url" value="${video.video_url || ""}" placeholder="Preenchido automaticamente após upload"></label>
    <label class="field-label">URL da capa<input class="cover-url" value="${video.cover_url || ""}" placeholder="Opcional"></label>
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

async function bulkUploadToLoop(files, containerId = "video-items") {
  toast(`Enviando ${files.length} vídeo(s)...`);
  let ok = 0;
  for (const file of files) {
    try {
      const uploaded = await uploadFile("/api/upload/video", file);
      addVideoRow({ video_url: uploaded.url }, containerId);
      ok++;
    } catch { /* continue */ }
  }
  toast(`${ok} vídeo(s) adicionados`);
  maybeAutoSaveBatch(containerId);
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
  const videos = [...document.querySelectorAll(".video-row")].map(row => ({
    video_url: row.querySelector(".video-url").value.trim(),
    cover_url: row.querySelector(".cover-url").value.trim(),
  })).filter(v => v.video_url);

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
  document.querySelectorAll(".tab[data-mode]").forEach(t => t.classList.toggle("active", t.dataset.mode === mode));
  document.getElementById("panel-loop")?.classList.toggle("hidden", mode !== "loop");
  document.getElementById("panel-recurring")?.classList.toggle("hidden", mode !== "recurring");
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
    limite_api: { cls: "limit", label: "Limite da API" },
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
        <div class="label">Limite / hora</div>
        <div class="value">${usage.posts_last_hour ?? 0} / ${usage.max_per_hour ?? "—"}</div>
        <div class="sub">${usage.remaining_hour ?? "—"} restantes na hora</div>
      </div>
      <div class="batch-monitor-stat">
        <div class="label">Limite / dia</div>
        <div class="value">${usage.posts_last_24h ?? 0} / ${usage.max_per_day ?? "—"}</div>
        <div class="sub">${usage.remaining_day ?? "—"} restantes no dia</div>
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

async function saveRecurringBatchSilent() {
  const accountId = document.getElementById("recurring-account")?.value
    || document.getElementById("loop-account")?.value;
  if (!accountId) return;
  const videos = getRecurringVideos();
  if (!videos.length) return;
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

async function saveLoopConfigSilent() {
  const accountId = document.getElementById("loop-account")?.value;
  if (!accountId) return;
  const videos = [...document.querySelectorAll("#video-items .video-row")].map(row => ({
    video_url: row.querySelector(".video-url").value.trim(),
    cover_url: row.querySelector(".cover-url").value.trim(),
  })).filter(v => v.video_url);
  if (!videos.length) return;
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

  setupDropzone("loop-video-dropzone", "loop-bulk-upload", files => bulkUploadToLoop(files, "video-items"));
  setupDropzone("recurring-dropzone", "recurring-upload", files => bulkUploadToLoop(files, "recurring-video-items"));

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
        <div class="meta">${u.role === "owner" ? "Proprietário" : "Administrador"} | ${u.is_active ? "Ativo" : "Inativo"}</div>
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
    if (me.role !== "owner") document.getElementById("nav-users")?.classList.add("hidden");
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
