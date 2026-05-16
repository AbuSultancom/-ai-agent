/* ── Helpers ── */
const $ = id => document.getElementById(id);

function getAuthHeader() {
  const token = localStorage.getItem('jwt_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function getActiveModel() {
  return localStorage.getItem('active_model') || '';
}

function setActiveModel(model) {
  localStorage.setItem('active_model', model);
  const sel = $('global-model-select');
  if (sel && model) sel.value = model;
  const badge = $('unified-model-badge');
  if (badge) badge.textContent = model || 'default model';
}

function escHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function renderMarkdown(text) {
  return text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`\n]+)`/g, '<code>$1</code>')
    .replace(/```[\s\S]*?```/g, m => `<pre>${escHtml(m.slice(3, -3).replace(/^\w+\n/, ''))}</pre>`)
    .replace(/\n/g, '<br>');
}

function showToast(msg, type = 'ok') {
  const t = $('toast');
  t.textContent = msg;
  t.style.borderColor = type === 'ok' ? 'var(--ok)' : 'var(--err)';
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2800);
}

/* ── Health check ── */
async function checkHealth() {
  try {
    const r = await fetch('/health', { headers: getAuthHeader() });
    $('health-dot').className = r.ok ? 'health-dot ok' : 'health-dot err';
  } catch { $('health-dot').className = 'health-dot err'; }
}
checkHealth();
setInterval(checkHealth, 30000);

/* ── Model loading ── */
async function loadModels() {
  try {
    const r = await fetch('/api/models', { headers: getAuthHeader() });
    const data = await r.json();
    const { claude = [], local = [], current_model = '' } = data;
    const active = getActiveModel() || current_model;

    let opts = '<option value="">Default</option>';
    if (claude.length) {
      opts += '<optgroup label="Claude Models">' +
        claude.map(m => `<option value="${escHtml(m.id)}">${escHtml(m.name || m.id)}</option>`).join('') +
        '</optgroup>';
    }
    if (local.length) {
      opts += '<optgroup label="Local (Ollama)">' +
        local.map(m => `<option value="${escHtml(m.name)}">${escHtml(m.name)}</option>`).join('') +
        '</optgroup>';
    }

    const sel = $('global-model-select');
    sel.innerHTML = opts;
    if (active) sel.value = active;

    const badge = $('unified-model-badge');
    if (badge) badge.textContent = active || (current_model ? current_model : 'default model');
  } catch {}
}
loadModels();

$('global-model-select').addEventListener('change', () => {
  setActiveModel($('global-model-select').value);
  if ($('global-model-select').value) showToast(`Model: ${$('global-model-select').value}`, 'ok');
});

/* ── Conversation state ── */
let conversationHistory = [];
let streaming = false;
let attachedFile = null;

/* ── Attachment handling ── */
$('attach-btn').addEventListener('click', () => $('attach-input').click());
$('attach-input').addEventListener('change', () => {
  const file = $('attach-input').files[0];
  if (!file) return;
  attachedFile = file;
  showAttachPreview(file);
  $('attach-input').value = '';
});

function showAttachPreview(file) {
  const preview = $('attach-preview');
  preview.innerHTML = '';

  const isImage = file.type.startsWith('image/');
  let el;

  if (isImage) {
    el = document.createElement('div');
    el.className = 'attach-thumb';
    const img = document.createElement('img');
    img.src = URL.createObjectURL(file);
    el.appendChild(img);
  } else {
    el = document.createElement('div');
    el.className = 'attach-chip';
    el.innerHTML = `<span>📎</span><span title="${escHtml(file.name)}">${escHtml(file.name)}</span>`;
  }

  const rm = document.createElement('button');
  rm.className = 'attach-remove';
  rm.textContent = '×';
  rm.addEventListener('click', clearAttachment);
  el.appendChild(rm);
  preview.appendChild(el);
}

function clearAttachment() {
  attachedFile = null;
  $('attach-preview').innerHTML = '';
}

/* ── Message rendering ── */
function scrollToBottom() {
  const msgs = $('chat-messages');
  msgs.scrollTop = msgs.scrollHeight;
}

function appendUserBubble(text, file) {
  const welcome = $('chat-welcome');
  if (welcome) welcome.remove();

  const row = document.createElement('div');
  row.className = 'umsg-row user';

  const avatar = document.createElement('div');
  avatar.className = 'umsg-avatar';
  avatar.textContent = '👤';

  const content = document.createElement('div');
  content.className = 'umsg-content';

  if (file) {
    if (file.type.startsWith('image/')) {
      const img = document.createElement('img');
      img.className = 'umsg-image';
      img.src = URL.createObjectURL(file);
      content.appendChild(img);
    } else {
      const chip = document.createElement('div');
      chip.className = 'umsg-file-chip';
      chip.innerHTML = `<span>📎</span><span>${escHtml(file.name)}</span>`;
      content.appendChild(chip);
    }
  }

  if (text) {
    const textEl = document.createElement('div');
    textEl.innerHTML = escHtml(text).replace(/\n/g, '<br>');
    content.appendChild(textEl);
  }

  row.appendChild(avatar);
  row.appendChild(content);
  $('chat-messages').appendChild(row);
  scrollToBottom();
}

function appendAssistantBubble() {
  const row = document.createElement('div');
  row.className = 'umsg-row assistant';

  const avatar = document.createElement('div');
  avatar.className = 'umsg-avatar';
  avatar.textContent = '🤖';

  const content = document.createElement('div');
  content.className = 'umsg-content';
  content.innerHTML = '<div class="typing-dots"><span></span><span></span><span></span></div>';

  row.appendChild(avatar);
  row.appendChild(content);
  $('chat-messages').appendChild(row);
  scrollToBottom();
  return content;
}

function appendToolCard(parentEl, name, args) {
  const card = document.createElement('div');
  card.className = 'tool-card';
  card.innerHTML = `
    <div class="tool-card-head" onclick="this.parentElement.classList.toggle('open')">
      <span>⚙️</span>
      <span class="tool-name">${escHtml(name)}</span>
      <span class="tool-args">${escHtml(args)}</span>
      <span class="tool-chevron">▶</span>
    </div>
    <div class="tool-body">
      <pre>${escHtml(args)}</pre>
    </div>`;
  parentEl.appendChild(card);
  scrollToBottom();
  return card;
}

/* ── Chip quick-send ── */
function chipSend(text) {
  $('unified-input').value = text;
  sendSmartMessage();
}

/* ── New chat ── */
function newChat() {
  conversationHistory = [];
  $('chat-messages').innerHTML = `
    <div id="chat-welcome" class="chat-welcome">
      <div class="welcome-icon">🤖</div>
      <h1>AI Agent</h1>
      <p>Ask anything · Upload an image · Attach a file</p>
      <div class="chip-row">
        <button class="chip" onclick="chipSend('List all Python files in the current directory')">📁 List files</button>
        <button class="chip" onclick="chipSend('Write a Hello World Python script and save it to /tmp/hello.py')">🐍 Python script</button>
        <button class="chip" onclick="chipSend('What tools and capabilities do you have?')">🛠️ Show tools</button>
        <button class="chip" onclick="chipSend('Summarize the project structure')">🔍 Analyze project</button>
      </div>
    </div>`;
  clearAttachment();
}
$('new-chat-btn').addEventListener('click', newChat);

/* ── Send ── */
async function sendSmartMessage() {
  const text = $('unified-input').value.trim();
  const file = attachedFile;
  if ((!text && !file) || streaming) return;

  $('unified-input').value = '';
  $('unified-input').style.height = 'auto';
  streaming = true;
  $('unified-send-btn').disabled = true;

  appendUserBubble(text, file);
  if (file) clearAttachment();

  conversationHistory.push({ role: 'user', content: text || `[Attached file: ${file?.name}]` });

  const content = appendAssistantBubble();
  let textAccum = '';

  try {
    const fd = new FormData();
    if (text) fd.append('message', text);
    fd.append('history', JSON.stringify(conversationHistory.slice(-20)));
    const model = getActiveModel();
    if (model) fd.append('model', model);
    if (file) fd.append('files', file);

    const res = await fetch('/api/smart/stream', {
      method: 'POST',
      headers: getAuthHeader(),
      body: fd,
    });

    if (!res.ok) {
      content.textContent = `Error: ${res.statusText}`;
      return;
    }

    content.innerHTML = '';
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let textEl = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value);
      for (const line of chunk.split('\n')) {
        if (!line.startsWith('data: ')) continue;
        const payload = line.slice(6).trim();
        if (payload === '[DONE]') break;
        try {
          const evt = JSON.parse(payload);
          if (evt.type === 'text') {
            textAccum += evt.content;
            if (!textEl) {
              textEl = document.createElement('div');
              content.appendChild(textEl);
            }
            textEl.innerHTML = renderMarkdown(escHtml(textAccum));
          } else if (evt.type === 'tool') {
            textEl = null;
            appendToolCard(content, evt.name, evt.args);
          } else if (evt.type === 'image') {
            const img = document.createElement('img');
            img.src = evt.url;
            img.style.cssText = 'max-width:100%;border-radius:8px;margin-top:8px;border:1px solid var(--border)';
            content.appendChild(img);
          }
          scrollToBottom();
        } catch {}
      }
    }

    conversationHistory.push({ role: 'assistant', content: textAccum || '(no response)' });
  } catch (err) {
    content.innerHTML = `<span style="color:var(--err)">Error: ${escHtml(err.message)}</span>`;
  } finally {
    streaming = false;
    $('unified-send-btn').disabled = false;
  }
}

$('unified-send-btn').addEventListener('click', sendSmartMessage);
$('unified-input').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendSmartMessage(); }
});
$('unified-input').addEventListener('input', function () {
  this.style.height = 'auto';
  this.style.height = Math.min(this.scrollHeight, 200) + 'px';
});
