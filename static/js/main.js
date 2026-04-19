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

function timeAgo(iso) {
  if (!iso) return '';
  const diff = (Date.now() - new Date(iso)) / 1000;
  if (diff < 60) return `${Math.round(diff)}ث`;
  if (diff < 3600) return `${Math.round(diff / 60)}د`;
  if (diff < 86400) return `${Math.round(diff / 3600)}س`;
  return `${Math.round(diff / 86400)}ي`;
}

function renderMarkdown(text) {
  return text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>');
}

function showToast(msg, type = 'ok') {
  const t = document.createElement('div');
  t.style.cssText = `position:fixed;bottom:24px;left:50%;transform:translateX(-50%);
    background:${type === 'ok' ? '#48bb78' : '#fc8181'};color:#fff;padding:10px 22px;
    border-radius:8px;font-size:14px;z-index:9999;box-shadow:0 4px 16px rgba(0,0,0,.4)`;
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 2800);
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
  btn.innerHTML = '⏳ جارٍ التنفيذ… <span class="spinner"></span>';
  taskOutput.textContent = '';

  try {
    const res = await APIJ('/api/task', { task });
    const { task_id } = await res.json();
    if (!task_id) throw new Error('لم يتم إنشاء المهمة');

    if (currentEventSource) currentEventSource.close();
    currentEventSource = new EventSource(`/api/task/${task_id}/stream`);
    currentEventSource.onmessage = e => {
      taskOutput.textContent += e.data;
      taskOutput.scrollTop = taskOutput.scrollHeight;
    };
    currentEventSource.addEventListener('done', e => {
      currentEventSource.close();
      btn.disabled = false;
      btn.textContent = '▶ تشغيل';
      loadTasks();
      showToast(e.data === 'completed' ? '✅ اكتملت المهمة' : '❌ فشلت المهمة', e.data === 'completed' ? 'ok' : 'err');
    });
    currentEventSource.onerror = () => {
      currentEventSource.close();
      btn.disabled = false;
      btn.textContent = '▶ تشغيل';
    };
  } catch (err) {
    taskOutput.textContent = `خطأ: ${err.message}`;
    btn.disabled = false;
    btn.textContent = '▶ تشغيل';
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
    if (!tasks.length) { list.innerHTML = '<p style="color:var(--muted);font-size:13px">لا توجد مهام بعد</p>'; return; }
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
  $('tab-tasks').scrollIntoView();
  API(`/api/task/${id}`).then(r => r.json()).then(t => {
    taskOutput.textContent = t.output || '(لا يوجد مخرجات)';
    taskOutput.scrollTop = taskOutput.scrollHeight;
  });
}

function escHtml(s) { return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

loadTasks();

/* ═══════════════════════════════════════
   TAB 2 — CHAT
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
  input.value = '';
  chatHistory.push({ role: 'user', content: text });
  renderChat();

  // Typing indicator
  const typing = document.createElement('div');
  typing.className = 'msg assistant typing';
  typing.textContent = 'يكتب…';
  $('chat-messages').appendChild(typing);
  $('chat-messages').scrollTop = $('chat-messages').scrollHeight;

  try {
    const res = await APIJ('/api/chat', { message: text, history: chatHistory.slice(-20) });
    const data = await res.json();
    typing.remove();
    const reply = data.reply || data.error || 'لا رد';
    chatHistory.push({ role: 'assistant', content: reply });
    localStorage.setItem('chat_history', JSON.stringify(chatHistory.slice(-60)));
    renderChat();
  } catch (err) {
    typing.remove();
    chatHistory.push({ role: 'assistant', content: `خطأ: ${err.message}` });
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
  box.textContent = 'جاري البحث…';
  try {
    const r = await APIJ('/api/memory/search', { query: q, n_results: 8 });
    const { results } = await r.json();
    if (!results.length) { box.textContent = 'لا توجد نتائج'; return; }
    box.innerHTML = results.map(r =>
      `<div style="margin-bottom:12px"><strong style="color:var(--accent2)">${escHtml(r.key)}</strong>` +
      `<span style="color:var(--muted);font-size:12px"> (${r.score || ''})</span><br>${escHtml(r.content)}</div>`
    ).join('<hr style="border-color:var(--border);margin:10px 0">');
  } catch (e) { box.textContent = `خطأ: ${e.message}`; }
});

$('memory-store-btn').addEventListener('click', async () => {
  const key = $('memory-key').value.trim();
  const content = $('memory-content').value.trim();
  if (!key || !content) return showToast('أدخل المفتاح والمحتوى', 'err');
  const r = await APIJ('/api/memory', { key, content });
  const data = await r.json();
  $('memory-store-result').textContent = data.stored ? `✅ تم حفظ: ${key}` : JSON.stringify(data);
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
    result.textContent = `جارٍ رفع ${file.name}…`;
    const fd = new FormData();
    fd.append('file', file);
    try {
      const r = await fetch('/api/rag/upload', { method: 'POST', body: fd, headers: getAuthHeader() });
      const data = await r.json();
      result.textContent = data.message || JSON.stringify(data);
      showToast(`✅ ${file.name} تم رفعه`, 'ok');
      loadDocs();
    } catch (e) { result.textContent = `خطأ: ${e.message}`; }
  }
}

$('rag-ask-btn').addEventListener('click', async () => {
  const q = $('rag-query').value.trim();
  if (!q) return;
  const box = $('rag-answer');
  box.textContent = 'جارٍ البحث في المستندات…';
  try {
    const r = await APIJ('/api/rag/query', { query: q });
    const data = await r.json();
    box.textContent = data.answer || data.error || 'لا توجد إجابة';
  } catch (e) { box.textContent = `خطأ: ${e.message}`; }
});

$('refresh-docs-btn').addEventListener('click', loadDocs);

async function loadDocs() {
  try {
    const r = await API('/api/rag/documents');
    const { documents } = await r.json();
    const list = $('docs-list');
    if (!documents.length) { list.innerHTML = '<p style="color:var(--muted);font-size:13px">لا توجد مستندات</p>'; return; }
    list.innerHTML = documents.map(d => `
      <div class="task-card">
        <div class="task-head">
          <span class="task-text">📄 ${escHtml(d.name)}</span>
          <span class="task-time">${d.chunks} قطعة</span>
          <button class="btn danger small" onclick="deleteDoc('${escHtml(d.name)}')">حذف</button>
        </div>
      </div>`).join('');
  } catch { }
}

async function deleteDoc(name) {
  await APIJ('/api/rag/documents', { name }, 'DELETE');
  loadDocs();
  showToast(`🗑️ تم حذف ${name}`);
}

loadDocs();

/* ═══════════════════════════════════════
   TAB 5 — SCHEDULER
═══════════════════════════════════════ */
$('sched-add-btn').addEventListener('click', async () => {
  const name = $('sched-name').value.trim();
  const task = $('sched-task').value.trim();
  const cron = $('sched-cron').value.trim();
  if (!name || !task || !cron) return showToast('أكمل جميع الحقول', 'err');
  const r = await APIJ('/api/scheduler/jobs', { name, task, cron });
  const data = await r.json();
  $('sched-result').textContent = data.id ? `✅ تمت الجدولة: ${data.id}` : JSON.stringify(data);
  $('sched-name').value = ''; $('sched-task').value = ''; $('sched-cron').value = '';
  loadJobs();
});

$('refresh-sched-btn').addEventListener('click', loadJobs);

async function loadJobs() {
  try {
    const r = await API('/api/scheduler/jobs');
    const { jobs } = await r.json();
    const list = $('sched-list');
    if (!jobs.length) { list.innerHTML = '<p style="color:var(--muted);font-size:13px">لا توجد مهام مجدولة</p>'; return; }
    list.innerHTML = jobs.map(j => `
      <div class="task-card">
        <div class="task-head">
          <span class="task-text">⏰ ${escHtml(j.name)} — <code style="font-size:12px">${escHtml(j.cron)}</code></span>
          <span class="task-time">${j.next_run ? 'التالي: ' + j.next_run : ''}</span>
          <button class="btn danger small" onclick="deleteJob('${j.id}')">حذف</button>
        </div>
        <div style="color:var(--muted);font-size:13px;margin-top:4px">${escHtml(j.task).slice(0,80)}</div>
      </div>`).join('');
  } catch { }
}

async function deleteJob(id) {
  await fetch(`/api/scheduler/jobs/${id}`, { method: 'DELETE', headers: getAuthHeader() });
  loadJobs();
}

loadJobs();
