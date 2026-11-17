const content = document.querySelector("#content");
const title = document.querySelector("#view-title");
let editingSourceId = null;
let cachedSources = [];

const views = {
  dashboard: ["總覽", "系統狀態與監控來源概況"],
  sources: ["Log 來源", "管理要讀取的檔案與查詢指令"],
  llm: ["LLM 設定", "摘要模型連線設定"],
  webhook: ["Webhook", "通知目的地設定"],
  summaries: ["分析結果", "查看最近產生的摘要"],
};

function render(view) {
  const [name, description] = views[view] || views.dashboard;
  title.textContent = name;
  document.querySelectorAll(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.view === view));
  if (view === "sources") return renderSources();
  if (view === "dashboard") return renderDashboard(description);
  if (view === "llm") return renderLLM();
  if (view === "summaries") return renderSummaries();
  content.innerHTML = `<div class="empty-state"><div class="empty-icon">✦</div><h2>${name}</h2><p>${description}</p><span class="coming-soon">即將推出</span></div>`;
}

async function renderDashboard(description) {
  let sources = [];
  let loadError = "";
  try {
    const response = await fetch("/api/log-sources");
    if (!response.ok) throw new Error(await response.text());
    sources = await response.json();
  } catch (error) {
    loadError = `無法載入 Log 來源：${escapeHtml(error.message)}`;
  }
  content.innerHTML = `
    <div class="welcome-row"><div><p class="lead">${description}</p><h2>${loadError ? "系統狀態需要檢查。" : "今天，系統運作正常。"}</h2>${loadError ? `<p class="form-message error">${loadError}</p>` : ""}</div><button class="primary" data-go-sources>管理 Log 來源 <span>→</span></button></div>
    <div class="stat-grid">
      <div class="stat-card"><span class="stat-icon blue">⌁</span><div><small>監控來源</small><strong>${sources.length}</strong><em>個已設定</em></div></div>
      <div class="stat-card"><span class="stat-icon green">●</span><div><small>啟用中</small><strong>${sources.filter((s) => s.enabled).length}</strong><em>正常運作</em></div></div>
      <div class="stat-card"><span class="stat-icon purple">✦</span><div><small>今日摘要</small><strong>—</strong><em>尚未開始分析</em></div></div>
    </div>
    <div class="dashboard-grid"><div class="panel"><div class="panel-heading"><div><h3>監控來源</h3><p>目前已設定的 Log</p></div><button class="icon-button" data-go-sources>查看全部 →</button></div>
      ${sources.length ? sources.slice(0, 5).map(sourceRow).join("") : '<div class="blank-row"><span class="blank-icon">⌁</span><div><strong>還沒有監控來源</strong><p>新增第一個 Log 來源開始使用。</p></div></div>'}
    </div><div class="panel quick-panel"><div class="panel-heading"><div><h3>快速開始</h3><p>三步驟完成第一次設定</p></div></div>
      <div class="step done"><b>1</b><div><strong>建立 Log 來源</strong><p>指定檔案或查詢指令</p></div></div>
      <div class="step"><b>2</b><div><strong>連接 LLM</strong><p>設定摘要模型 API</p></div></div>
      <div class="step"><b>3</b><div><strong>開始分析</strong><p>查看摘要與通知</p></div></div>
    </div></div>`;
  document.querySelectorAll("[data-go-sources]").forEach((button) => button.addEventListener("click", () => render("sources")));
}

function sourceRow(source) {
  return `<div class="mini-source"><span class="source-type ${source.source_type}">${source.source_type === "command" ? "⌘" : "▤"}</span><div><strong>${escapeHtml(source.name)}</strong><small>${escapeHtml(source.source_type === "command" ? source.command : source.path)}</small></div><span class="status ${source.enabled ? "on" : "off"}">${source.enabled ? "啟用" : "停用"}</span></div>`;
}

async function renderSources() {
  content.innerHTML = `<div class="section-intro"><div><p class="lead">設定要讀取的檔案或查詢指令，檔案可填主機上的絕對路徑，儲存後可立即預覽。</p><h2>你的 Log 來源</h2></div><div class="source-header-actions"><button id="analyze-all" class="primary">✦ 摘要全部</button><button id="new-source" class="secondary">＋ 新增來源</button></div></div><div id="source-editor" hidden></div><div class="panel source-panel"><div class="panel-heading"><div><h3>來源列表</h3><p id="source-count">載入中...</p></div><button class="icon-button" id="refresh-sources">↻ 重新整理</button></div><div id="source-list" class="source-list">載入中...</div></div>`;
  document.querySelector("#new-source").addEventListener("click", () => showEditor());
  document.querySelector("#refresh-sources").addEventListener("click", loadSources);
  document.querySelector("#analyze-all").addEventListener("click", analyzeAll);
  await loadSources();
}

function showEditor(source = null) {
  editingSourceId = source?.id || null;
  const editor = document.querySelector("#source-editor");
  editor.hidden = false;
  editor.innerHTML = `<div class="panel editor-panel"><div class="panel-heading"><div><span class="eyebrow">${editingSourceId ? "EDIT SOURCE" : "NEW SOURCE"}</span><h3>${editingSourceId ? "編輯 Log 來源" : "新增 Log 來源"}</h3></div><button class="icon-button" id="close-editor">×</button></div>
    <form id="source-form"><div class="form-grid"><label>顯示名稱<input name="name" required placeholder="例如：Nginx Error" value="${escapeAttr(source?.name)}"></label><label>來源類型<select name="source_type" id="source-type"><option value="file" ${source?.source_type !== "command" ? "selected" : ""}>檔案路徑</option><option value="command" ${source?.source_type === "command" ? "selected" : ""}>查詢指令</option></select></label></div>
    <label id="path-field">檔案路徑<input name="path" placeholder="/var/log/nginx/error.log" value="${escapeAttr(source?.path)}"></label><label id="command-field" hidden>查詢指令<textarea name="command" placeholder="docker logs --tail 500 container-name">${escapeHtml(source?.command || "")}</textarea></label>
    <div class="form-grid three"><label>擷取方式<select name="read_mode"><option value="tail_lines" ${source?.read_mode !== "tail_bytes" ? "selected" : ""}>最後 N 行</option><option value="tail_bytes" ${source?.read_mode === "tail_bytes" ? "selected" : ""}>最後 N Bytes</option></select></label><label>行數<input name="tail_lines" type="number" min="1" value="${source?.tail_lines || 500}"></label><label>Bytes<input name="tail_bytes" type="number" min="1" value="${source?.tail_bytes || 262144}"></label></div>
    <div class="form-grid"><label>Include 關鍵字<textarea name="include_patterns" placeholder="每行一個，留空代表全部">${escapeHtml(source?.include_patterns || "")}</textarea></label><label>Exclude 關鍵字<textarea name="exclude_patterns" placeholder="每行一個，符合的內容會排除">${escapeHtml(source?.exclude_patterns || "")}</textarea></label></div>
    <label>分析週期（分鐘）<input name="schedule_minutes" type="number" min="1" value="${source?.schedule_minutes || 5}"></label>
    <div class="form-footer"><label class="toggle"><input name="enabled" type="checkbox" ${source?.enabled !== false ? "checked" : ""}><span></span>啟用這個來源</label><div><button type="button" class="secondary" id="cancel-editor">取消</button><button type="submit" class="primary">${editingSourceId ? "儲存變更" : "建立來源"}</button></div></div><p id="source-message" class="form-message"></p></form></div>`;
  document.querySelector("#source-type").addEventListener("change", toggleSourceFields);
  document.querySelector("#source-form").addEventListener("submit", saveSource);
  document.querySelector("#close-editor").addEventListener("click", hideEditor);
  document.querySelector("#cancel-editor").addEventListener("click", hideEditor);
  toggleSourceFields({ target: document.querySelector("#source-type") });
  editor.scrollIntoView({ behavior: "smooth", block: "start" });
}

function hideEditor() { editingSourceId = null; const editor = document.querySelector("#source-editor"); editor.hidden = true; editor.innerHTML = ""; }

async function loadSources() {
  const response = await fetch("/api/log-sources");
  if (!response.ok) {
    const message = document.querySelector("#source-count");
    if (message) message.textContent = `載入失敗：${await response.text()}`;
    return;
  }
  cachedSources = await response.json();
  document.querySelector("#source-count").textContent = `${cachedSources.length} 個來源`;
  document.querySelector("#source-list").innerHTML = cachedSources.length ? cachedSources.map((source) => `<div class="source-card"><div class="source-card-main"><div class="source-card-title"><span class="source-type ${source.source_type}">${source.source_type === "command" ? "⌘" : "▤"}</span><strong>${escapeHtml(source.name)}</strong><span class="badge">${source.source_type === "command" ? "指令" : "檔案"}</span><span class="status ${source.enabled ? "on" : "off"}">${source.enabled ? "啟用" : "停用"}</span></div><code>${escapeHtml(source.source_type === "command" ? source.command : source.path)}</code><small>${source.read_mode === "tail_lines" ? `最後 ${source.tail_lines} 行` : `最後 ${source.tail_bytes} bytes`}　·　每 ${source.schedule_minutes} 分鐘</small></div><div class="source-actions"><button class="secondary" data-preview="${source.id}">預覽</button><button class="primary" data-analyze="${source.id}">開始分析</button><button class="secondary" data-edit="${source.id}">編輯</button><button class="danger" data-delete="${source.id}">刪除</button></div><pre id="preview-${source.id}" hidden></pre></div>`).join("") : '<div class="blank-row"><span class="blank-icon">⌁</span><div><strong>尚未建立來源</strong><p>點擊右上角「新增來源」開始設定。</p></div></div>';
  document.querySelectorAll("[data-preview]").forEach((button) => button.addEventListener("click", () => previewSource(button.dataset.preview)));
  document.querySelectorAll("[data-analyze]").forEach((button) => button.addEventListener("click", () => analyzeSource(button)));
  document.querySelectorAll("[data-edit]").forEach((button) => button.addEventListener("click", () => showEditor(cachedSources.find((item) => item.id === Number(button.dataset.edit)))));
  document.querySelectorAll("[data-delete]").forEach((button) => button.addEventListener("click", () => deleteSource(button.dataset.delete)));
}

async function saveSource(event) {
  event.preventDefault();
  const form = new FormData(event.target);
  const payload = Object.fromEntries(form.entries());
  payload.enabled = form.get("enabled") === "on"; payload.path = payload.source_type === "file" ? payload.path : ""; payload.command = payload.source_type === "command" ? payload.command : null; payload.tail_lines = Number(payload.tail_lines); payload.tail_bytes = Number(payload.tail_bytes); payload.schedule_minutes = Number(payload.schedule_minutes);
  const id = editingSourceId; const response = await fetch(id ? `/api/log-sources/${id}` : "/api/log-sources", { method: id ? "PUT" : "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload) });
  const message = document.querySelector("#source-message");
  if (!response.ok) { message.textContent = `儲存失敗：${await response.text()}`; message.className = "form-message error"; return; }
  hideEditor(); await loadSources();
}

function toggleSourceFields(event) { const command = event.target.value === "command"; document.querySelector("#path-field").hidden = command; document.querySelector("#command-field").hidden = !command; }
async function previewSource(id) { const target = document.querySelector(`#preview-${id}`); target.hidden = false; target.textContent = "讀取中..."; const response = await fetch(`/api/log-sources/${id}/preview`); target.textContent = response.ok ? (await response.json()).content || "(沒有符合條件的內容)" : `預覽失敗：${await response.text()}`; }
async function deleteSource(id) { if (!window.confirm("確定要刪除此 Log 來源？")) return; const response = await fetch(`/api/log-sources/${id}`, { method: "DELETE" }); if (response.ok) loadSources(); else window.alert(`刪除失敗：${await response.text()}`); }
async function analyzeSource(button) { button.disabled = true; button.textContent = "分析中..."; const response = await fetch(`/api/log-sources/${button.dataset.analyze}/analyze`, { method: "POST" }); button.disabled = false; button.textContent = "開始分析"; if (response.ok) { render("summaries"); } else window.alert(`分析失敗：${await response.text()}`); }
async function analyzeAll() { const button = document.querySelector("#analyze-all"); button.disabled = true; button.textContent = "摘要全部分析中..."; const response = await fetch("/api/analyze-all", { method: "POST" }); button.disabled = false; button.textContent = "✦ 摘要全部"; if (response.ok) render("summaries"); else window.alert(`全體摘要失敗：${await response.text()}`); }
async function renderLLM() {
  const response = await fetch("/api/settings/llm");
  if (!response.ok) {
    content.innerHTML = `<div class="empty-state"><div class="empty-icon">!</div><h2>LLM 設定載入失敗</h2><p>${escapeHtml(await response.text())}</p></div>`;
    return;
  }
  const config = await response.json();
  content.innerHTML = `<div class="section-intro"><div><p class="lead">設定 Ollama、模型與所有分析提示詞。</p><h2>LLM 連線與提示詞</h2></div></div><div class="panel editor-panel"><form id="llm-form"><div class="form-grid"><label>Base URL<input name="base_url" required value="${escapeAttr(config.base_url)}"></label><label>模型<input name="model" required value="${escapeAttr(config.model)}"></label></div><div class="form-grid three"><label>Temperature<input name="temperature" type="number" min="0" max="2" step="0.1" value="${config.temperature}"></label><label>最大輸入 Bytes<input name="max_input_bytes" type="number" min="1000" value="${config.max_input_bytes}"></label><label>API Key（可選）<input name="api_key" type="password" placeholder="${config.has_api_key ? "已設定，留空保持不變" : "Ollama 通常不需要"}"></label></div><label>System Prompt<textarea name="system_prompt">${escapeHtml(config.system_prompt)}</textarea><small class="muted">會放在每次請求的 system message。</small><label>分析提示詞<textarea name="analysis_prompt">${escapeHtml(config.analysis_prompt)}</textarea><small class="muted">必須包含 <code>{log_text}</code>，它會被替換為實際 Log。</small><label>連線測試提示詞<textarea name="connection_test_prompt">${escapeHtml(config.connection_test_prompt)}</textarea><small class="muted">按「測試連線」時使用。</small><div class="form-footer"><span id="current-model" class="muted">目前模型：${escapeHtml(config.model)}</span><div><button type="button" class="secondary" id="test-llm">測試連線</button><button class="primary">儲存設定</button></div></div><p id="llm-message" class="form-message"></p></form></div>`;
  document.querySelector("#llm-form").addEventListener("submit", saveLLM);
  document.querySelector("#test-llm").addEventListener("click", testLLM);
}
async function saveLLM(event) { event.preventDefault(); const data = Object.fromEntries(new FormData(event.target).entries()); data.temperature = Number(data.temperature); data.max_input_bytes = Number(data.max_input_bytes); data.api_key = data.api_key || null; const response = await fetch("/api/settings/llm", { method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data) }); const message = document.querySelector("#llm-message"); if (response.ok) { document.querySelector("#current-model").textContent = `目前模型：${data.model}`; message.textContent = "LLM 設定已儲存。"; message.className = "form-message"; } else { message.textContent = `儲存失敗：${await response.text()}`; message.className = "form-message error"; } }
async function testLLM() { const button = document.querySelector("#test-llm"); button.disabled = true; button.textContent = "測試中..."; const response = await fetch("/api/settings/llm/test", { method: "POST" }); button.disabled = false; button.textContent = "測試連線"; const message = document.querySelector("#llm-message"); message.textContent = response.ok ? "連線成功，模型可用。" : `連線失敗：${await response.text()}`; message.className = response.ok ? "form-message" : "form-message error"; }
function displaySummaryValue(value) { if (value === null || value === undefined) return ""; if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value); if (Array.isArray(value)) return value.map(displaySummaryValue).filter(Boolean).join("、"); if (typeof value === "object") return Object.entries(value).map(([key, item]) => `${key}：${displaySummaryValue(item)}`).filter(Boolean).join("；"); return String(value); }
async function renderSummaries(filters = {}) { const params = new URLSearchParams(); Object.entries(filters).forEach(([key, value]) => { if (value) params.set(key, value); }); const response = await fetch(`/api/summaries?${params}`); const summaries = await response.json(); content.innerHTML = `<div class="section-intro"><div><p class="lead">搜尋、檢視與清理已保存的模型摘要。</p><h2>分析結果</h2></div><div class="source-header-actions"><button class="danger" id="delete-filtered">刪除目前結果</button><button class="primary" data-go-sources>回到 Log 來源</button></div></div><div class="panel search-panel"><form id="summary-search"><input name="keyword" placeholder="搜尋摘要或 Log 內容" value="${escapeAttr(filters.keyword || "")}"><select name="severity"><option value="">全部嚴重程度</option><option value="info" ${filters.severity === "info" ? "selected" : ""}>Info</option><option value="warning" ${filters.severity === "warning" ? "selected" : ""}>Warning</option><option value="critical" ${filters.severity === "critical" ? "selected" : ""}>Critical</option></select><select name="scope"><option value="">所有摘要</option><option value="all" ${filters.all_sources ? "selected" : ""}>全體摘要</option></select><button class="secondary">搜尋</button></form></div><div class="panel source-panel"><div class="panel-heading"><div><h3>結果列表</h3><p>${summaries.length} 筆結果</p></div></div><div id="summary-list">${summaries.length ? summaries.map((item) => { let result = {}; try { result = JSON.parse(item.result_json || "{}"); } catch (_) {} const report = result.log_analysis_report; const summaryText = item.error_message || displaySummaryValue(result.summary || result.analysis_summary || result.log_summary || result["摘要"] || result["事件摘要"] || result["分析摘要"] || (report && (report.summary || report["摘要"]))) || (item.status === "failed" ? "模型分析失敗（點擊查看錯誤與 raw）" : "無摘要"); const events = result.key_events || result.key_activities || result.events || result["事件"] || result["關鍵活動"] || result["觀察到的活動"] || result["關鍵事件"] || []; const eventText = displaySummaryValue(events); const lineCount = item.input_preview ? item.input_preview.split(/\r?\n/).length : 0; return `<div class="summary-card" data-summary-id="${item.id}" role="button" tabindex="0"><div class="summary-meta"><span class="badge">${item.log_source_id === null ? "全體摘要" : item.severity || result.severity || "unknown"}</span><span>${new Date(item.created_at).toLocaleString()}</span><button class="danger small-danger" data-delete-summary="${item.id}">刪除</button></div><h3>${escapeHtml(summaryText)}</h3><p>${escapeHtml(eventText)}</p><small>${item.status} · ${lineCount} 行輸入 · 點擊查看錯誤與 raw</small></div>`; }).join("") : '<div class="blank-row"><span class="blank-icon">✦</span><div><strong>查無分析結果</strong><p>調整條件或到 Log 來源開始分析。</p></div></div>'}</div></div>`; document.querySelector("[data-go-sources]").addEventListener("click", () => render("sources")); document.querySelector("#summary-search").addEventListener("submit", (event) => { event.preventDefault(); const data = Object.fromEntries(new FormData(event.target).entries()); renderSummaries({ keyword: data.keyword, severity: data.severity, all_sources: data.scope === "all" }); }); document.querySelectorAll("[data-delete-summary]").forEach((button) => button.addEventListener("click", (event) => { event.stopPropagation(); deleteSummary(button.dataset.deleteSummary, filters); })); document.querySelectorAll("[data-summary-id]").forEach((card) => { card.addEventListener("click", () => renderSummaryDetail(card.dataset.summaryId, filters)); card.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") renderSummaryDetail(card.dataset.summaryId, filters); }); }); document.querySelector("#delete-filtered").addEventListener("click", () => deleteFiltered(filters)); }
async function renderSummaryDetail(id, filters = {}) { const response = await fetch(`/api/summaries/${id}`); if (!response.ok) { content.innerHTML = `<div class="empty-state"><h2>無法載入分析紀錄</h2><p>${escapeHtml(await response.text())}</p></div>`; return; } const item = await response.json(); const errorPanel = item.error_message ? `<div class="panel raw-panel error-panel"><div class="panel-heading"><div><h3>分析錯誤</h3><p>模型回應失敗，但原始請求與回應已保存</p></div></div><pre>${escapeHtml(item.error_message)}</pre></div>` : ""; content.innerHTML = `<div class="section-intro"><div><p class="lead">分析紀錄 #${item.id} 的完整原始交換內容。</p><h2>${item.status === "failed" ? "模型分析失敗" : "原生輸入與輸出"}</h2></div><button class="primary" id="back-summaries">返回分析結果</button></div>${errorPanel}<div class="panel raw-panel"><div class="panel-heading"><div><h3>Raw Input</h3><p>包含完整 system prompt、user prompt 與實際請求參數</p></div></div><pre>${escapeHtml(item.raw_input || "(此紀錄沒有保存 raw input)")}</pre></div><div class="panel raw-panel"><div class="panel-heading"><div><h3>Raw Output</h3><p>LLM API 原始回應</p></div></div><pre>${escapeHtml(item.raw_output || "(此紀錄沒有保存 raw output)")}</pre></div>`; document.querySelector("#back-summaries").addEventListener("click", () => renderSummaries(filters)); }
async function deleteSummary(id, filters) { if (!window.confirm("確定刪除此分析結果？")) return; const response = await fetch(`/api/summaries/${id}`, { method: "DELETE" }); if (response.ok) renderSummaries(filters); else window.alert(`刪除失敗：${await response.text()}`); }
async function deleteFiltered(filters) { if (!window.confirm("確定刪除目前查詢結果？此操作無法復原。")) return; const params = new URLSearchParams(); if (filters.all_sources) params.set("all_sources", "true"); if (filters.source_id) params.set("source_id", filters.source_id); const response = await fetch(`/api/summaries?${params}`, { method: "DELETE" }); if (response.ok) renderSummaries(filters); else window.alert(`刪除失敗：${await response.text()}`); }
function escapeHtml(value = "") { return String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" })[char]); }
function escapeAttr(value = "") { return escapeHtml(value); }

document.querySelectorAll(".nav-item").forEach((button) => button.addEventListener("click", () => render(button.dataset.view)));
fetch("/api/health").then((response) => response.json()).then((data) => { document.querySelector("#health").textContent = data.status === "ok" ? "服務正常" : "服務異常"; }).catch(() => { document.querySelector("#health").textContent = "無法連線"; document.querySelector("#health-dot").classList.add("off"); });
render("dashboard");
