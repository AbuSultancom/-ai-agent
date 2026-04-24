/* ───────── Helpers ───────── */
const $ = id => document.getElementById(id);
const API = path => fetch(path, { headers: getAuthHeader() });
const APIJ = (path, body, method = 'POST') =>
  fetch(path, {
    method,
    headers: { 'Content-Type': 'application/json', ...getAuthHeader() },
    body: JSON.stringify(body),
  });

function getAuthHeader() {
  const token = localStorage.getItem('jwt_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function getActiveModel() {
  return localStorage.getItem('active_model') || '';
}

function setActiveModel(model) {
  localStorage.setItem('active_model', model);
  const gSel = $('global-model-select');
  if (gSel && model) gSel.value = model;
  const cSel = $('chat-model-select');
  if (cSel && model) cSel.value = model;
}

function timeAgo(iso) {
  if (!iso) return '';
  const diff = (Date.now() - new Date(iso)) / 1000;
  if (diff < 60) return `${Math.round(diff)}s`;
  if (diff < 3600) return `${Math.round(diff / 60)}m`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h`;
  return `${Math.round(diff / 86400)}d`;
}

function renderMarkdown(text) {
  return text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>');
}

function escHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function showToast(msg, type = 'ok') {
  const t = $('toast');
  t.textContent = msg;
  t.style.borderColor = type === 'ok' ? 'var(--ok)' : 'var(--err)';
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2800);
}

/* ───────── Health check ───────── */
async function checkHealth() {
  try {
    const r = await API('/health');
    $('health-dot').className = r.ok ? 'health-dot ok' : 'health-dot err';
  } catch { $('health-dot').className = 'health-dot err'; }
}
checkHealth();
setInterval(checkHealth, 30000);

/* ───────── Tab navigation ───────── */
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(s => s.classList.remove('active'));
    btn.classList.add('active');
    $(`tab-${btn.dataset.tab}`).classList.add('active');
    if (btn.dataset.tab === 'models') loadModels();
    if (btn.dataset.tab === 'monitoring') loadMonitoring();
  });
});

/* ═══════════════════════════════════════
   TAB 1 — TASKS
═══════════════════════════════════════ */
const taskOutput = $('task-output');
let currentEventSource = null;

async function runTask() {
  const task = $('task-input').value.trim();
  if (!task) return;
  const btn = $('run-task-btn');
  btn.disabled = true;
  btn.innerHTML = '⏳ Running… <span class="spinner"></span>';
  taskOutput.textContent = '';

  try {
    const model = getActiveModel();
    const body = { task };
    if (model) body.model = model;
    const res = await APIJ('/api/task', body);
    const { task_id } = await res.json();
    if (!task_id) throw new Error('Task creation failed');

    if (currentEventSource) currentEventSource.close();
    currentEventSource = new EventSource(`/api/task/${task_id}/stream`);
    currentEventSource.onmessage = e => {
      taskOutput.textContent += e.data;
      taskOutput.scrollTop = taskOutput.scrollHeight;
    };
    currentEventSource.addEventListener('done', e => {
      currentEventSource.close();
      btn.disabled = false;
      btn.textContent = '▶ Run';
      loadTasks();
      showToast(e.data === 'completed' ? '✅ Task completed' : '❌ Task failed',
        e.data === 'completed' ? 'ok' : 'err');
    });
    currentEventSource.onerror = () => {
      currentEventSource.close();
      btn.disabled = false;
      btn.textContent = '▶ Run';
    };
  } catch (err) {
    taskOutput.textContent = `Error: ${err.message}`;
    btn.disabled = false;
    btn.textContent = '▶ Run';
  }
}

$('run-task-btn').addEventListener('click', runTask);
$('task-input').addEventListener('keydown', e => { if (e.ctrlKey && e.key === 'Enter') runTask(); });
$('clear-output-btn').addEventListener('click', () => { taskOutput.textContent = ''; });
$('refresh-tasks-btn').addEventListener('click', loadTasks);

async function loadTasks() {
  try {
    const r = await API('/api/tasks');
    const { tasks } = await r.json();
    const list = $('tasks-list');
    if (!tasks.length) { list.innerHTML = '<p style="color:var(--muted);font-size:13px">No tasks yet</p>'; return; }
    list.innerHTML = tasks.map(t => `
      <div class="task-card" onclick="showTaskOutput('${t.id}','${escHtml(t.task)}')">
        <div class="task-head">
          <span class="task-text">${escHtml(t.task)}</span>
          <span class="task-time">${timeAgo(t.created_at)}</span>
          <span class="badge ${t.status}">${t.status}</span>
        </div>
      </div>`).join('');
  } catch { }
}

function showTaskOutput(id, taskText) {
  $('task-input').value = taskText;
  API(`/api/task/${id}`).then(r => r.json()).then(t => {
    taskOutput.textContent = t.output || '(no output)';
    taskOutput.scrollTop = taskOutput.scrollHeight;
  });
}

loadTasks();

/* ═══════════════════════════════════════
   TAB 2 — CHAT (with Personas)
═══════════════════════════════════════ */
let chatHistory = JSON.parse(localStorage.getItem('chat_history') || '[]');

function renderChat() {
  const msgs = $('chat-messages');
  msgs.innerHTML = chatHistory.map(m => `
    <div class="msg ${m.role}">${renderMarkdown(escHtml(m.content))}</div>`).join('');
  msgs.scrollTop = msgs.scrollHeight;
}

async function sendChat() {
  const input = $('chat-input');
  const text = input.value.trim();
  if (!text) return;
  const personaId = $('persona-select').value;
  const modelOverride = $('chat-model-select').value || getActiveModel() || '';
  input.value = '';
  chatHistory.push({ role: 'user', content: text });
  renderChat();

  const typing = document.createElement('div');
  typing.className = 'msg assistant typing';
  typing.textContent = 'Typing…';
  $('chat-messages').appendChild(typing);
  $('chat-messages').scrollTop = $('chat-messages').scrollHeight;

  try {
    const endpoint = personaId !== 'default' ? '/api/chat/persona' : '/api/chat';
    const body = personaId !== 'default'
      ? { message: text, persona_id: personaId }
      : { message: text, history: chatHistory.slice(-20) };
    if (modelOverride) body.model = modelOverride;
    const res = await APIJ(endpoint, body);
    const data = await res.json();
    typing.remove();
    const reply = data.reply || data.error || 'No response';
    chatHistory.push({ role: 'assistant', content: reply });
    localStorage.setItem('chat_history', JSON.stringify(chatHistory.slice(-60)));
    renderChat();
  } catch (err) {
    typing.remove();
    chatHistory.push({ role: 'assistant', content: `Error: ${err.message}` });
    renderChat();
  }
}

$('chat-send-btn').addEventListener('click', sendChat);
$('chat-input').addEventListener('keydown', e => { if (e.key === 'Enter') sendChat(); });
$('chat-clear-btn').addEventListener('click', () => {
  chatHistory = [];
  localStorage.removeItem('chat_history');
  renderChat();
  APIJ('/api/chat/clear', {});
});

renderChat();

/* ═══════════════════════════════════════
   TAB 3 — MEMORY
═══════════════════════════════════════ */
$('memory-search-btn').addEventListener('click', async () => {
  const q = $('memory-query').value.trim();
  if (!q) return;
  const box = $('memory-results');
  box.textContent = 'Searching…';
  try {
    const r = await APIJ('/api/memory/search', { query: q, n_results: 8 });
    const { results } = await r.json();
    if (!results.length) { box.textContent = 'No results found'; return; }
    box.innerHTML = results.map(r =>
      `<div style="margin-bottom:12px"><strong style="color:var(--accent2)">${escHtml(r.key)}</strong>` +
      `<span style="color:var(--muted);font-size:12px"> (${r.score || ''})</span><br>${escHtml(r.content)}</div>`
    ).join('<hr style="border-color:var(--border);margin:10px 0">');
  } catch (e) { box.textContent = `Error: ${e.message}`; }
});

$('memory-store-btn').addEventListener('click', async () => {
  const key = $('memory-key').value.trim();
  const content = $('memory-content').value.trim();
  if (!key || !content) return showToast('Key and content are required', 'err');
  const r = await APIJ('/api/memory', { key, content });
  const data = await r.json();
  $('memory-store-result').textContent = data.stored ? `✅ Saved: ${key}` : JSON.stringify(data);
  $('memory-key').value = '';
  $('memory-content').value = '';
});

/* ═══════════════════════════════════════
   TAB 4 — RAG
═══════════════════════════════════════ */
const uploadArea = $('upload-area');
const fileInput = $('file-input');

uploadArea.addEventListener('click', () => fileInput.click());
uploadArea.addEventListener('dragover', e => { e.preventDefault(); uploadArea.classList.add('dragover'); });
uploadArea.addEventListener('dragleave', () => uploadArea.classList.remove('dragover'));
uploadArea.addEventListener('drop', e => {
  e.preventDefault();
  uploadArea.classList.remove('dragover');
  uploadFiles(e.dataTransfer.files);
});
fileInput.addEventListener('change', () => uploadFiles(fileInput.files));

async function uploadFiles(files) {
  const result = $('upload-result');
  for (const file of files) {
    result.textContent = `Uploading ${file.name}…`;
    const fd = new FormData();
    fd.append('file', file);
    try {
      const r = await fetch('/api/rag/upload', { method: 'POST', body: fd, headers: getAuthHeader() });
      const data = await r.json();
      result.textContent = data.message || JSON.stringify(data);
      showToast(`✅ ${file.name} uploaded`, 'ok');
      loadDocs();
    } catch (e) { result.textContent = `Error: ${e.message}`; }
  }
}

$('rag-ask-btn').addEventListener('click', async () => {
  const q = $('rag-query').value.trim();
  if (!q) return;
  const box = $('rag-answer');
  box.textContent = 'Searching documents…';
  try {
    const r = await APIJ('/api/rag/query', { query: q });
    const data = await r.json();
    box.textContent = data.answer || data.error || 'No answer found';
  } catch (e) { box.textContent = `Error: ${e.message}`; }
});

$('refresh-docs-btn').addEventListener('click', loadDocs);

async function loadDocs() {
  try {
    const r = await API('/api/rag/documents');
    const { documents } = await r.json();
    const list = $('docs-list');
    if (!documents.length) { list.innerHTML = '<p style="color:var(--muted);font-size:13px">No documents yet</p>'; return; }
    list.innerHTML = documents.map(d => `
      <div class="task-card">
        <div class="task-head">
          <span class="task-text">📄 ${escHtml(d.name)}</span>
          <span class="task-time">${d.chunks} chunks</span>
          <button class="btn danger small" onclick="deleteDoc('${escHtml(d.name)}')">Delete</button>
        </div>
      </div>`).join('');
  } catch { }
}

async function deleteDoc(name) {
  await APIJ('/api/rag/documents', { name }, 'DELETE');
  loadDocs();
  showToast(`🗑️ ${name} deleted`);
}

loadDocs();

/* ═══════════════════════════════════════
   TAB 5 — VISION
═══════════════════════════════════════ */
let visionFile = null;
const visionArea = $('vision-upload-area');
const visionInput = $('vision-file-input');
const visionPreview = $('vision-preview');

visionArea.addEventListener('click', () => visionInput.click());
visionArea.addEventListener('dragover', e => { e.preventDefault(); visionArea.classList.add('dragover'); });
visionArea.addEventListener('dragleave', () => visionArea.classList.remove('dragover'));
visionArea.addEventListener('drop', e => {
  e.preventDefault();
  visionArea.classList.remove('dragover');
  if (e.dataTransfer.files[0]) setVisionFile(e.dataTransfer.files[0]);
});
visionInput.addEventListener('change', () => { if (visionInput.files[0]) setVisionFile(visionInput.files[0]); });

function setVisionFile(file) {
  visionFile = file;
  const url = URL.createObjectURL(file);
  visionPreview.src = url;
  visionPreview.style.display = 'block';
}

$('vision-analyze-btn').addEventListener('click', async () => {
  if (!visionFile) return showToast('Select an image first', 'err');
  const box = $('vision-result');
  box.textContent = 'Analyzing…';
  const fd = new FormData();
  fd.append('image', visionFile);
  const q = $('vision-question').value.trim();
  if (q) fd.append('question', q);
  try {
    const r = await fetch('/api/vision/analyze', { method: 'POST', body: fd, headers: getAuthHeader() });
    const data = await r.json();
    box.textContent = data.analysis || data.error || 'No result';
  } catch (e) { box.textContent = `Error: ${e.message}`; }
});

$('vision-ocr-btn').addEventListener('click', async () => {
  if (!visionFile) return showToast('Select an image first', 'err');
  const box = $('vision-result');
  box.textContent = 'Extracting text…';
  const fd = new FormData();
  fd.append('image', visionFile);
  try {
    const r = await fetch('/api/vision/ocr', { method: 'POST', body: fd, headers: getAuthHeader() });
    const data = await r.json();
    box.textContent = data.text || data.error || 'No text found';
  } catch (e) { box.textContent = `Error: ${e.message}`; }
});

$('vision-url-btn').addEventListener('click', async () => {
  const url = $('vision-url').value.trim();
  if (!url) return showToast('Enter image URL', 'err');
  const box = $('vision-url-result');
  box.textContent = 'Analyzing…';
  try {
    const r = await APIJ('/api/vision/analyze', { url, question: $('vision-url-question').value.trim() });
    const data = await r.json();
    box.textContent = data.analysis || data.error || 'No result';
  } catch (e) { box.textContent = `Error: ${e.message}`; }
});

/* ═══════════════════════════════════════
   TAB 6 — DATA ANALYSIS
═══════════════════════════════════════ */
let dataFile = null;
const dataArea = $('data-upload-area');
const dataInput = $('data-file-input');

dataArea.addEventListener('click', () => dataInput.click());
dataArea.addEventListener('dragover', e => { e.preventDefault(); dataArea.classList.add('dragover'); });
dataArea.addEventListener('dragleave', () => dataArea.classList.remove('dragover'));
dataArea.addEventListener('drop', e => {
  e.preventDefault();
  dataArea.classList.remove('dragover');
  if (e.dataTransfer.files[0]) { dataFile = e.dataTransfer.files[0]; dataArea.querySelector('span').textContent = `📊 ${dataFile.name}`; }
});
dataInput.addEventListener('change', () => {
  if (dataInput.files[0]) { dataFile = dataInput.files[0]; dataArea.querySelector('span').textContent = `📊 ${dataFile.name}`; }
});

$('data-analyze-btn').addEventListener('click', async () => {
  if (!dataFile) return showToast('Select a CSV or Excel file', 'err');
  const box = $('data-result');
  box.textContent = 'Analyzing…';
  const fd = new FormData();
  fd.append('file', dataFile);
  const q = $('data-question').value.trim();
  if (q) fd.append('question', q);
  try {
    const r = await fetch('/api/data/analyze', { method: 'POST', body: fd, headers: getAuthHeader() });
    const data = await r.json();
    box.textContent = data.answer || data.error || JSON.stringify(data);
  } catch (e) { box.textContent = `Error: ${e.message}`; }
});

$('data-summary-btn').addEventListener('click', async () => {
  if (!dataFile) return showToast('Select a CSV or Excel file', 'err');
  const box = $('data-result');
  box.textContent = 'Loading…';
  const fd = new FormData();
  fd.append('file', dataFile);
  try {
    const r = await fetch('/api/data/upload', { method: 'POST', body: fd, headers: getAuthHeader() });
    const data = await r.json();
    box.textContent = data.summary || data.error || JSON.stringify(data);
  } catch (e) { box.textContent = `Error: ${e.message}`; }
});

$('chart-btn').addEventListener('click', async () => {
  if (!dataFile) return showToast('Select a CSV or Excel file', 'err');
  const resultDiv = $('chart-result');
  resultDiv.innerHTML = '<p style="color:var(--muted)">Generating chart…</p>';
  const fd = new FormData();
  fd.append('file', dataFile);
  fd.append('chart_type', $('chart-type').value);
  fd.append('x_col', $('chart-x').value.trim());
  fd.append('y_col', $('chart-y').value.trim());
  try {
    const r = await fetch('/api/data/chart', { method: 'POST', body: fd, headers: getAuthHeader() });
    const data = await r.json();
    if (data.url) {
      resultDiv.innerHTML = `<img src="${data.url}" alt="chart" />`;
    } else {
      resultDiv.textContent = data.error || JSON.stringify(data);
    }
  } catch (e) { resultDiv.textContent = `Error: ${e.message}`; }
});

/* ═══════════════════════════════════════
   TAB 7 — PERSONAS
═══════════════════════════════════════ */
$('refresh-personas-btn').addEventListener('click', loadPersonas);

async function loadPersonas() {
  try {
    const r = await API('/api/personas');
    const { personas } = await r.json();
    const grid = $('personas-list');
    grid.innerHTML = personas.map(p => `
      <div class="persona-card" onclick="selectPersona('${p.id}')">
        <div class="p-emoji">${p.emoji || '🤖'}</div>
        <div class="p-name">${escHtml(p.name)}</div>
        <div class="p-desc">${escHtml(p.description || '')}</div>
        ${p.builtin ? '' : `<button class="btn danger small p-badge" onclick="deletePersona(event,'${p.id}')">Delete</button>`}
      </div>`).join('');

    const sel = $('persona-select');
    const existingValues = [...sel.options].map(o => o.value);
    personas.filter(p => !p.builtin && !existingValues.includes(p.id)).forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = `${p.emoji || '🤖'} ${p.name}`;
      sel.appendChild(opt);
    });
  } catch { }
}

function selectPersona(id) {
  $('persona-select').value = id;
  document.querySelector('[data-tab="chat"]').click();
  showToast(`Persona selected: ${id}`, 'ok');
}

async function deletePersona(evt, id) {
  evt.stopPropagation();
  const r = await fetch(`/api/personas/${id}`, { method: 'DELETE', headers: getAuthHeader() });
  const data = await r.json();
  if (data.deleted) { showToast('Deleted', 'ok'); loadPersonas(); }
  else showToast(data.error || 'Error', 'err');
}

$('persona-create-btn').addEventListener('click', async () => {
  const pid = $('persona-id').value.trim();
  const name = $('persona-name').value.trim();
  const emoji = $('persona-emoji').value.trim() || '🤖';
  const desc = $('persona-desc').value.trim();
  const system = $('persona-system').value.trim();
  if (!pid || !name || !system) return showToast('ID, name, and system prompt are required', 'err');
  const r = await APIJ('/api/personas', { id: pid, name, description: desc, system, emoji });
  const data = await r.json();
  $('persona-create-result').textContent = data.id ? `✅ Created: ${data.name}` : JSON.stringify(data);
  if (data.id) { loadPersonas(); $('persona-id').value = ''; $('persona-name').value = ''; $('persona-system').value = ''; }
});

loadPersonas();

/* ═══════════════════════════════════════
   TAB 8 — PROMPT TEMPLATES
═══════════════════════════════════════ */
$('refresh-templates-btn').addEventListener('click', loadTemplates);

async function loadTemplates() {
  try {
    const r = await API('/api/templates');
    const { templates } = await r.json();
    const list = $('templates-list');
    list.innerHTML = templates.map(t => `
      <div class="template-card">
        <div class="tmpl-info">
          <div class="tmpl-name">${escHtml(t.name)}</div>
          <div class="tmpl-desc">${escHtml(t.description || '')}</div>
          <div class="tmpl-vars">Variables: ${(t.variables || []).map(v => `{{${v}}}`).join(', ')}</div>
        </div>
        <div style="display:flex;gap:6px;flex-shrink:0">
          <button class="btn secondary small" onclick="selectTemplate('${t.id}')">Use</button>
          ${t.builtin ? '' : `<button class="btn danger small" onclick="deleteTemplate('${t.id}')">Delete</button>`}
        </div>
      </div>`).join('');

    const sel = $('template-select');
    sel.innerHTML = '<option value="">— Select a template —</option>' +
      templates.map(t => `<option value="${t.id}">${escHtml(t.name)}</option>`).join('');
  } catch { }
}

function selectTemplate(id) {
  $('template-select').value = id;
  buildTemplateVarsForm(id);
}

$('template-select').addEventListener('change', () => {
  buildTemplateVarsForm($('template-select').value);
});

async function buildTemplateVarsForm(id) {
  if (!id) { $('template-vars-form').innerHTML = ''; return; }
  try {
    const r = await API(`/api/templates/${id}`);
    const t = await r.json();
    $('template-vars-form').innerHTML = (t.variables || []).map(v =>
      `<div><label style="color:var(--muted);font-size:13px;display:block;margin-bottom:4px">{{${v}}}</label>
       <input type="text" id="tvar-${v}" placeholder="${v}" /></div>`
    ).join('');
  } catch { }
}

$('template-run-btn').addEventListener('click', async () => {
  const id = $('template-select').value;
  if (!id) return showToast('Select a template', 'err');
  const vars = collectTemplateVars();
  const box = $('template-result');
  box.textContent = 'Running…';
  try {
    const r = await APIJ(`/api/templates/${id}/run`, { variables: vars });
    const data = await r.json();
    box.textContent = data.output || data.error || JSON.stringify(data);
  } catch (e) { box.textContent = `Error: ${e.message}`; }
});

$('template-preview-btn').addEventListener('click', async () => {
  const id = $('template-select').value;
  if (!id) return showToast('Select a template', 'err');
  const vars = collectTemplateVars();
  try {
    const r = await APIJ(`/api/templates/${id}/render`, { variables: vars });
    const data = await r.json();
    $('template-result').textContent = data.rendered || data.error || JSON.stringify(data);
  } catch (e) { $('template-result').textContent = `Error: ${e.message}`; }
});

function collectTemplateVars() {
  const vars = {};
  document.querySelectorAll('#template-vars-form input').forEach(inp => {
    const key = inp.id.replace('tvar-', '');
    vars[key] = inp.value;
  });
  return vars;
}

$('new-tmpl-btn').addEventListener('click', async () => {
  const name = $('new-tmpl-name').value.trim();
  const tmpl = $('new-tmpl-text').value.trim();
  const desc = $('new-tmpl-desc').value.trim();
  if (!name || !tmpl) return showToast('Name and template body are required', 'err');
  const r = await APIJ('/api/templates', { name, template: tmpl, description: desc });
  const data = await r.json();
  $('new-tmpl-result').textContent = data.id ? `✅ Saved: ${data.name}` : JSON.stringify(data);
  if (data.id) { loadTemplates(); $('new-tmpl-name').value = ''; $('new-tmpl-text').value = ''; }
});

async function deleteTemplate(id) {
  const r = await fetch(`/api/templates/${id}`, { method: 'DELETE', headers: getAuthHeader() });
  const data = await r.json();
  if (data.deleted) { showToast('Deleted', 'ok'); loadTemplates(); }
  else showToast(data.error || 'Error', 'err');
}

loadTemplates();

/* ═══════════════════════════════════════
   TAB 9 — BATCH
═══════════════════════════════════════ */
$('batch-run-btn').addEventListener('click', async () => {
  const lines = $('batch-input').value.trim().split('\n').map(l => l.trim()).filter(Boolean);
  if (!lines.length) return showToast('Enter at least one task', 'err');
  const box = $('batch-result');
  const btn = $('batch-run-btn');
  btn.disabled = true;
  btn.innerHTML = '⏳ Running… <span class="spinner"></span>';
  box.textContent = `Running ${lines.length} tasks in parallel…`;
  try {
    const body = { tasks: lines };
    const model = getActiveModel();
    if (model) body.model = model;
    const r = await APIJ('/api/batch', body);
    const data = await r.json();
    if (data.error) { box.textContent = `Error: ${data.error}`; return; }
    box.innerHTML = `<strong>✅ ${data.completed} completed | ❌ ${data.failed} failed</strong>\n\n` +
      data.results.map((res, i) =>
        `--- Task ${i + 1} [${res.status}] ---\n${res.task}\n\n${res.output || res.error || ''}`
      ).join('\n\n═══════════════════\n\n');
  } catch (e) { box.textContent = `Error: ${e.message}`; }
  finally { btn.disabled = false; btn.textContent = '▶ Run All'; }
});

/* ═══════════════════════════════════════
   TAB 10 — SCHEDULER
═══════════════════════════════════════ */
$('sched-add-btn').addEventListener('click', async () => {
  const name = $('sched-name').value.trim();
  const task = $('sched-task').value.trim();
  const cron = $('sched-cron').value.trim();
  if (!name || !task || !cron) return showToast('All fields are required', 'err');
  const r = await APIJ('/api/scheduler/jobs', { name, task, cron });
  const data = await r.json();
  $('sched-result').textContent = data.id ? `✅ Scheduled: ${data.id}` : JSON.stringify(data);
  $('sched-name').value = ''; $('sched-task').value = ''; $('sched-cron').value = '';
  loadJobs();
});

$('refresh-sched-btn').addEventListener('click', loadJobs);

async function loadJobs() {
  try {
    const r = await API('/api/scheduler/jobs');
    const { jobs } = await r.json();
    const list = $('sched-list');
    if (!jobs.length) { list.innerHTML = '<p style="color:var(--muted);font-size:13px">No scheduled jobs</p>'; return; }
    list.innerHTML = jobs.map(j => `
      <div class="task-card">
        <div class="task-head">
          <span class="task-text">⏰ ${escHtml(j.name)} — <code style="font-size:12px">${escHtml(j.cron)}</code></span>
          <span class="task-time">${j.next_run ? 'Next: ' + j.next_run : ''}</span>
          <button class="btn danger small" onclick="deleteJob('${j.id}')">Delete</button>
        </div>
        <div style="color:var(--muted);font-size:13px;margin-top:4px">${escHtml(j.task).slice(0, 80)}</div>
      </div>`).join('');
  } catch { }
}

async function deleteJob(id) {
  await fetch(`/api/scheduler/jobs/${id}`, { method: 'DELETE', headers: getAuthHeader() });
  loadJobs();
}

loadJobs();

/* ═══════════════════════════════════════
   TAB 11 — MODELS
═══════════════════════════════════════ */
async function loadModels() {
  const grid = $('models-grid');
  const status = $('models-status');
  grid.innerHTML = '<p style="color:var(--muted)">Loading models…</p>';
  try {
    const r = await API('/api/models');
    const data = await r.json();
    const { claude = [], local = [], ollama_available = false, current_model = '' } = data;

    status.textContent = ollama_available
      ? `✅ Ollama connected — ${local.length} local model(s) available`
      : '⚠️ Ollama not running — only Claude models available';

    const activeModel = getActiveModel() || current_model;
    let html = '';

    if (claude.length) {
      html += `<div style="grid-column:1/-1;color:var(--muted);font-size:12px;margin-top:4px">── Claude (Anthropic) ──</div>`;
      html += claude.map(m => `
        <div class="model-card ${activeModel === m.id ? 'active-model' : ''}">
          <div class="m-name">${escHtml(m.name || m.id)}</div>
          <div class="m-provider">Anthropic</div>
          <div class="m-size">${escHtml(m.description || '')}</div>
          <div class="m-actions">
            <button class="btn secondary small" onclick="useModel('${escHtml(m.id)}')">Use</button>
          </div>
        </div>`).join('');
    }

    if (local.length) {
      html += `<div style="grid-column:1/-1;color:var(--muted);font-size:12px;margin-top:8px">── Local (Ollama) ──</div>`;
      html += local.map(m => `
        <div class="model-card ${activeModel === m.name ? 'active-model' : ''}">
          <div class="m-name">${escHtml(m.name)}</div>
          <div class="m-provider">Local / Ollama</div>
          <div class="m-size">${m.size ? (m.size / 1e9).toFixed(1) + ' GB' : ''}</div>
          <div class="m-actions">
            <button class="btn secondary small" onclick="useModel('${escHtml(m.name)}')">Use</button>
            <button class="btn danger small" onclick="deleteLocalModel('${escHtml(m.name)}')">Delete</button>
          </div>
        </div>`).join('');
    }

    if (!claude.length && !local.length) {
      html = '<p style="color:var(--muted)">No models found. Check your API key and Ollama status.</p>';
    }

    grid.innerHTML = html;
    loadAllModelSelects(data);
  } catch (e) {
    grid.textContent = `Error: ${e.message}`;
  }
}

function useModel(modelId) {
  setActiveModel(modelId);
  showToast(`Active model: ${modelId}`, 'ok');
  loadModels();
}

async function deleteLocalModel(name) {
  if (!confirm(`Delete local model "${name}"?`)) return;
  try {
    const r = await APIJ('/api/models/delete', { name });
    const data = await r.json();
    if (data.deleted) { showToast(`Deleted: ${name}`, 'ok'); loadModels(); }
    else showToast(data.error || 'Delete failed', 'err');
  } catch (e) { showToast(`Error: ${e.message}`, 'err'); }
}

function loadAllModelSelects(data) {
  const { claude = [], local = [], current_model = '' } = data || {};
  const activeModel = getActiveModel() || current_model;

  const buildOptions = () => {
    let opts = '<option value="">Default (config)</option>';
    if (claude.length) {
      opts += `<optgroup label="Claude Models">`;
      opts += claude.map(m => `<option value="${escHtml(m.id)}">${escHtml(m.name || m.id)}</option>`).join('');
      opts += `</optgroup>`;
    }
    if (local.length) {
      opts += `<optgroup label="Local (Ollama)">`;
      opts += local.map(m => `<option value="${escHtml(m.name)}">${escHtml(m.name)}</option>`).join('');
      opts += `</optgroup>`;
    }
    return opts;
  };

  const gSel = $('global-model-select');
  const cSel = $('chat-model-select');
  const opts = buildOptions();
  if (gSel) { gSel.innerHTML = opts; if (activeModel) gSel.value = activeModel; }
  if (cSel) { cSel.innerHTML = opts; if (activeModel) cSel.value = activeModel; }
}

/* Pull a local model via SSE */
$('pull-model-btn').addEventListener('click', pullModel);

async function pullModel() {
  const customVal = $('pull-model-custom').value.trim();
  const selectVal = $('pull-model-select').value;
  const modelName = customVal || selectVal;
  if (!modelName) return showToast('Select or type a model name', 'err');

  const box = $('pull-result');
  const btn = $('pull-model-btn');
  btn.disabled = true;
  btn.innerHTML = '⏳ Pulling… <span class="spinner"></span>';
  box.textContent = `Pulling ${modelName}…\n`;

  try {
    const res = await fetch('/api/models/pull', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getAuthHeader() },
      body: JSON.stringify({ name: modelName }),
    });

    if (!res.ok) {
      const err = await res.json();
      box.textContent = `Error: ${err.error || res.statusText}`;
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value);
      const lines = chunk.split('\n');
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const text = line.slice(6);
          if (text && text !== '[DONE]') {
            box.textContent += text + '\n';
            box.scrollTop = box.scrollHeight;
          }
        }
      }
    }
    showToast(`✅ ${modelName} pulled successfully`, 'ok');
    loadModels();
  } catch (e) {
    box.textContent += `Error: ${e.message}`;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Pull';
  }
}

/* Global model select change handler */
$('global-model-select').addEventListener('change', () => {
  const val = $('global-model-select').value;
  setActiveModel(val);
  if (val) showToast(`Active model: ${val}`, 'ok');
});

$('refresh-models-btn').addEventListener('click', loadModels);

/* Load models on startup to populate selects */
(async () => {
  try {
    const r = await API('/api/models');
    const data = await r.json();
    loadAllModelSelects(data);
  } catch { }
})();

/* ═══════════════════════════════════════
   TAB 12 — MONITORING
═══════════════════════════════════════ */
$('refresh-stats-btn').addEventListener('click', loadMonitoring);

async function loadMonitoring() {
  try {
    const [statsR, reqR, hourR] = await Promise.all([
      API('/api/monitoring/stats'),
      API('/api/monitoring/requests?n=30'),
      API('/api/monitoring/hourly'),
    ]);
    const stats = await statsR.json();
    const { requests } = await reqR.json();
    const { hourly } = await hourR.json();

    $('stats-grid').innerHTML = [
      { label: 'Total Requests', value: stats.total_requests },
      { label: 'Input Tokens', value: (stats.total_input_tokens || 0).toLocaleString() },
      { label: 'Output Tokens', value: (stats.total_output_tokens || 0).toLocaleString() },
      { label: 'Cost (USD)', value: `$${(stats.total_cost_usd || 0).toFixed(4)}` },
      { label: 'Errors', value: stats.errors || 0 },
    ].map(s => `
      <div class="stat-card">
        <div class="stat-value">${escHtml(String(s.value))}</div>
        <div class="stat-label">${s.label}</div>
      </div>`).join('');

    $('requests-list').textContent = requests.map(r =>
      `[${r.ts.slice(11, 19)}] ${r.endpoint} — ${r.input_tokens}↑${r.output_tokens}↓ — $${r.cost_usd} — ${r.latency_ms}ms${r.error ? ' ❌' : ''}`
    ).join('\n');

    $('hourly-list').textContent = hourly.map(h =>
      `${h.hour}: ${h.requests} requests | ${h.tokens} tokens | $${h.cost.toFixed(4)}`
    ).join('\n') || 'No data yet';
  } catch (e) { $('stats-grid').textContent = `Error: ${e.message}`; }
}
