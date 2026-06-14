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

  zone.addEventListener("dragover", e => { e.preventDefault(); zone.classList.add("dragover"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
  zone.addEventListener("drop", e => {
    e.preventDefault();
    zone.classList.remove("dragover");
    onFiles([...e.dataTransfer.files]);
  });
  input.addEventListener("change", () => onFiles([...input.files]));
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
    <div class="stat-card"><div class="value">${data.total_accounts}/${data.max_accounts}</div><div class="label">Contas</div></div>
    <div class="stat-card"><div class="value">${data.total_posts}</div><div class="label">Posts publicados</div></div>
    <div class="stat-card"><div class="value">${data.total_errors}</div><div class="label">Erros</div></div>
    <div class="stat-card"><div class="value">${data.running_loops}</div><div class="label">Loops ativos</div></div>
    <div class="stat-card"><div class="value">${data.pending_schedule || 0}</div><div class="label">Agendados</div></div>
  `;

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
  el.innerHTML = accountsCache.map(a => {
    const fb = a.fallback_account_id
      ? accountsCache.find(x => x.id === a.fallback_account_id)?.name || `#${a.fallback_account_id}`
      : "não";
    return `
    <div class="account-item">
      <div>
        <strong>${a.name}</strong> @${a.username || "—"}
        <div class="meta">${healthBadge(a.health_status)} | ${a.usage.posts_last_24h}/${a.max_posts_per_day}d | Proxy: ${a.proxy_url ? "sim" : "não"} | Contingência: ${fb}</div>
      </div>
      <div class="actions">
        <button class="btn secondary" onclick="editAccount(${a.id})">Editar</button>
        <button class="btn secondary" onclick="checkHealth(${a.id})">Saúde</button>
        <button class="btn danger" onclick="deleteAccount(${a.id})">Excluir</button>
      </div>
    </div>
  `}).join("") || "<p class='hint'>Nenhuma conta cadastrada</p>";
}

function populateAccountSelects() {
  ["post-account", "loop-account", "pub-account", "sch-account"].forEach(id => {
    const sel = document.getElementById(id);
    if (!sel) return;
    const current = sel.value;
    sel.innerHTML = accountsCache.map(a => `<option value="${a.id}">${a.name}</option>`).join("");
    if (current) sel.value = current;
  });

  ["fallback_account_id", "sch-fallback"].forEach(id => {
    const sel = document.getElementById(id);
    if (!sel) return;
    const current = sel.value;
    const accountId = document.getElementById("account-id")?.value;
    sel.innerHTML = `<option value="">Nenhuma</option>` + accountsCache
      .filter(a => String(a.id) !== String(accountId))
      .map(a => `<option value="${a.id}">${a.name}</option>`).join("");
    if (current) sel.value = current;
  });
}

function resetAccountForm() {
  document.getElementById("account-form").reset();
  document.getElementById("account-id").value = "";
  document.getElementById("form-title").textContent = "Nova conta";
  document.getElementById("is_active").checked = true;
  updateCaptionCount();
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
  document.getElementById("default_caption").value = a.default_caption || "";
  document.getElementById("is_active").checked = a.is_active;
  populateAccountSelects();
  document.getElementById("fallback_account_id").value = a.fallback_account_id || "";
  updateCaptionCount();
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
    default_caption: document.getElementById("default_caption").value,
    is_active: document.getElementById("is_active").checked,
    fallback_account_id: document.getElementById("fallback_account_id").value
      ? +document.getElementById("fallback_account_id").value
      : null,
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
  await api(`/api/accounts/${id}`, { method: "DELETE" });
  toast("Conta excluída");
  loadAccounts();
}

async function checkHealth(id) {
  const h = await api(`/api/accounts/${id}/health`);
  toast(`Saúde: ${h.status} — ${h.message}`);
  loadAccounts();
}

function updateCaptionCount() {
  const el = document.getElementById("default_caption");
  const count = document.getElementById("caption-count");
  if (el && count) count.textContent = el.value.length;
}

function initAccountsPage() {
  loadAccounts();
  const cap = document.getElementById("default_caption");
  if (cap) cap.addEventListener("input", updateCaptionCount);
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

function addVideoRow(video = {}) {
  const container = document.getElementById("video-items");
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
  });

  row.querySelector(".cover-file").addEventListener("change", async e => {
    const file = e.target.files[0];
    if (!file) return;
    const uploaded = await uploadFile("/api/upload/image", file);
    row.querySelector(".cover-url").value = uploaded.url;
    toast("Capa adicionada");
  });
}

async function bulkUploadToLoop(files) {
  toast(`Enviando ${files.length} vídeo(s)...`);
  const result = await uploadFiles("/api/upload/videos", files);
  result.uploaded.forEach(v => addVideoRow({ video_url: v.url }));
  toast(`${result.uploaded.length} vídeo(s) adicionados ao loop`);
}

async function loadLoopConfig() {
  const accountId = document.getElementById("loop-account")?.value;
  if (!accountId) return;
  const data = await api(`/api/loop/${accountId}`);
  document.getElementById("batch_size").value = data.batch_size;
  document.getElementById("interval_seconds").value = data.interval_seconds;
  document.getElementById("loop-caption").value = data.caption || "";

  const container = document.getElementById("video-items");
  container.innerHTML = "";
  (data.videos || []).forEach(v => addVideoRow(v));

  const status = document.getElementById("loop-status");
  if (status) {
    status.textContent = [
      `Status: ${data.is_running ? "RODANDO (contínuo)" : "Parado"}`,
      `Índice: ${data.current_index}`,
      `Lotes completados: ${data.batches_completed}`,
      `Total posts: ${data.total_posts}`,
      `Último erro: ${data.last_error || "nenhum"}`,
    ].join("\n");
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
    }),
  });
  toast("Loop salvo");
  loadLoopConfig();
}

async function startLoop() {
  const accountId = document.getElementById("loop-account").value;
  try {
    await saveLoop({ preventDefault: () => {} });
    const res = await api(`/api/loop/${accountId}/start`, { method: "POST" });
    toast(res.message);
    loadLoopConfig();
  } catch (err) {
    toast(err.message, "error");
  }
}

async function stopLoop() {
  const accountId = document.getElementById("loop-account").value;
  await api(`/api/loop/${accountId}/stop`, { method: "POST" });
  toast("Loop parado");
  loadLoopConfig();
}

async function initLoopPage() {
  await loadAccounts();
  setupDropzone("loop-video-dropzone", "loop-bulk-upload", bulkUploadToLoop);
  const loopCap = document.getElementById("loop-caption");
  const loopCounter = document.getElementById("loop-caption-count");
  if (loopCap && loopCounter) {
    loopCap.addEventListener("input", () => { loopCounter.textContent = loopCap.value.length; });
  }
  loadLoopConfig();
}

// --- Schedule ---

let scheduleMode = "batch";
let scheduleListChart = null;
let schVideoCounter = 0;
let schCustomCounter = 0;

function setScheduleMode(mode) {
  scheduleMode = mode;
  document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.dataset.mode === mode));
  document.getElementById("mode-batch")?.classList.toggle("hidden", mode !== "batch");
  document.getElementById("mode-custom")?.classList.toggle("hidden", mode !== "custom");
}

function addScheduleVideoRow(video = {}) {
  const container = document.getElementById("sch-video-rows");
  if (!container) return;
  const id = ++schVideoCounter;
  const row = document.createElement("div");
  row.className = "video-row";
  row.innerHTML = `
    <div class="video-row-header">
      <strong>Vídeo</strong>
      <button type="button" class="btn danger" onclick="this.closest('.video-row').remove()">Remover</button>
    </div>
    <label class="field-label">URL do vídeo<input class="sch-video-url" value="${video.video_url || ""}"></label>
    <label class="field-label">URL da capa<input class="sch-cover-url" value="${video.cover_url || ""}"></label>
    <div class="upload-mini">
      <input type="file" class="sch-video-file" accept="video/*" hidden id="svf-${id}">
      <input type="file" class="sch-cover-file" accept="image/*" hidden id="scf-${id}">
      <button type="button" class="btn secondary" onclick="document.getElementById('svf-${id}').click()">Upload vídeo</button>
      <button type="button" class="btn secondary" onclick="document.getElementById('scf-${id}').click()">Upload capa</button>
    </div>
  `;
  container.appendChild(row);

  row.querySelector(".sch-video-file").addEventListener("change", async e => {
    const file = e.target.files[0];
    if (!file) return;
    toast("Enviando vídeo...");
    const uploaded = await uploadFile("/api/upload/video", file);
    row.querySelector(".sch-video-url").value = uploaded.url;
    toast("Vídeo adicionado");
  });

  row.querySelector(".sch-cover-file").addEventListener("change", async e => {
    const file = e.target.files[0];
    if (!file) return;
    const uploaded = await uploadFile("/api/upload/image", file);
    row.querySelector(".sch-cover-url").value = uploaded.url;
    toast("Capa adicionada");
  });
}

function addCustomScheduleRow(item = {}) {
  const container = document.getElementById("sch-custom-rows");
  if (!container) return;
  const id = ++schCustomCounter;
  const row = document.createElement("div");
  row.className = "video-row";
  row.innerHTML = `
    <div class="video-row-header">
      <strong>Item agendado</strong>
      <button type="button" class="btn danger" onclick="this.closest('.video-row').remove()">Remover</button>
    </div>
    <label class="field-label">Data/hora<input type="datetime-local" class="sch-custom-at" value="${item.scheduled_at || ""}" required></label>
    <label class="field-label">URL do vídeo<input class="sch-custom-video" value="${item.video_url || ""}"></label>
    <label class="field-label">URL da capa<input class="sch-custom-cover" value="${item.cover_url || ""}"></label>
    <label class="field-label">Legenda<textarea class="sch-custom-caption" rows="2">${item.caption || ""}</textarea></label>
    <div class="upload-mini">
      <input type="file" class="sch-custom-video-file" accept="video/*" hidden id="cvf-${id}">
      <button type="button" class="btn secondary" onclick="document.getElementById('cvf-${id}').click()">Upload vídeo</button>
    </div>
  `;
  container.appendChild(row);

  row.querySelector(".sch-custom-video-file").addEventListener("change", async e => {
    const file = e.target.files[0];
    if (!file) return;
    const uploaded = await uploadFile("/api/upload/video", file);
    row.querySelector(".sch-custom-video").value = uploaded.url;
    toast("Vídeo adicionado");
  });
}

function toIsoLocal(dtLocal) {
  if (!dtLocal) return "";
  const d = new Date(dtLocal);
  return d.toISOString();
}

async function submitSchedule(e) {
  e.preventDefault();
  const accountId = +document.getElementById("sch-account").value;
  const fallbackVal = document.getElementById("sch-fallback").value;
  const body = {
    name: document.getElementById("sch-name").value,
    account_id: accountId,
    fallback_account_id: fallbackVal ? +fallbackVal : null,
  };

  if (scheduleMode === "batch") {
    const videos = [...document.querySelectorAll("#sch-video-rows .video-row")].map(row => ({
      video_url: row.querySelector(".sch-video-url").value.trim(),
      cover_url: row.querySelector(".sch-cover-url").value.trim(),
    })).filter(v => v.video_url);
    if (!videos.length) return toast("Adicione pelo menos 1 vídeo", "error");
    body.start_at = toIsoLocal(document.getElementById("sch-start").value);
    body.interval_minutes = +document.getElementById("sch-interval").value;
    body.caption = document.getElementById("sch-caption").value;
    body.videos = videos;
  } else {
    const items = [...document.querySelectorAll("#sch-custom-rows .video-row")].map(row => ({
      scheduled_at: toIsoLocal(row.querySelector(".sch-custom-at").value),
      video_url: row.querySelector(".sch-custom-video").value.trim(),
      cover_url: row.querySelector(".sch-custom-cover").value.trim(),
      caption: row.querySelector(".sch-custom-caption").value,
    })).filter(i => i.video_url && i.scheduled_at);
    if (!items.length) return toast("Adicione itens com horário e vídeo", "error");
    body.items = items;
  }

  try {
    const res = await api("/api/schedule/batch", { method: "POST", body: JSON.stringify(body) });
    toast(`${res.created} vídeo(s) agendado(s)`);
    document.getElementById("schedule-form").reset();
    document.getElementById("sch-video-rows").innerHTML = "";
    document.getElementById("sch-custom-rows").innerHTML = "";
    addScheduleVideoRow();
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
    `).join("") : "<p class='hint'>Nenhum agendamento ainda</p>";
  }
}

async function initSchedulePage() {
  await loadAccounts();
  populateAccountSelects();
  addScheduleVideoRow();
  addCustomScheduleRow();

  const cap = document.getElementById("sch-caption");
  const counter = document.getElementById("sch-caption-count");
  if (cap && counter) cap.addEventListener("input", () => { counter.textContent = cap.value.length; });

  const bulk = document.getElementById("sch-bulk-upload");
  if (bulk) {
    bulk.addEventListener("change", async () => {
      const files = [...bulk.files];
      toast(`Enviando ${files.length} vídeo(s)...`);
      for (const file of files) {
        try {
          const uploaded = await uploadFile("/api/upload/video", file);
          addScheduleVideoRow({ video_url: uploaded.url });
        } catch { /* continue */ }
      }
      bulk.value = "";
      toast("Upload concluído");
    });
  }

  const start = document.getElementById("sch-start");
  if (start) {
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    start.value = now.toISOString().slice(0, 16);
  }

  loadScheduleList();
  setInterval(loadScheduleList, 20000);
}

// --- Settings ---

async function initSettingsPage() {
  const data = await api("/api/settings");
  document.getElementById("max_accounts").value = data.max_accounts;
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
        max_accounts: +document.getElementById("max_accounts").value,
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
