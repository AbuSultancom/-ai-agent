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
  // Fenced code blocks with language detection
  text = text.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    const language = lang || 'text';
    const highlighted = (typeof Prism !== 'undefined' && Prism.languages[language])
      ? Prism.highlight(code.trim(), Prism.languages[language], language)
      : escHtml(code.trim());
    return `<pre class="language-${language}"><code class="language-${language}">${highlighted}</code></pre>`;
  });
  // Inline code
  text = text.replace(/`([^`\n]+)`/g, '<code>$1</code>');
  // Bold
  text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  // Newlines (but not inside pre blocks)
  text = text.replace(/\n/g, '<br>');
  return text;
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

/* ── Conversation history (localStorage) ── */
const HISTORY_KEY = 'ai_agent_chats';

function loadStoredChats() {
  try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]'); } catch { return []; }
}

function saveCurrentChat() {
  if (!conversationHistory.length) return;
  const chats = loadStoredChats();
  const title = conversationHistory[0]?.content?.slice(0, 60) || 'Chat';
  const id = Date.now().toString();
  chats.unshift({ id, title, messages: conversationHistory, ts: new Date().toLocaleString() });
  localStorage.setItem(HISTORY_KEY, JSON.stringify(chats.slice(0, 50)));
}

function renderHistoryList() {
  const list = $('history-list');
  const chats = loadStoredChats();
  if (!chats.length) {
    list.innerHTML = '<div class="history-empty">No previous chats</div>';
    return;
  }
  list.innerHTML = chats.map(c => `
    <div class="history-item" onclick="loadChat('${c.id}')">
      <div class="hi-title">${escHtml(c.title)}</div>
      <div class="hi-meta">
        <span>${c.ts}</span>
        <button class="hi-del" onclick="deleteChat(event,'${c.id}')">🗑</button>
      </div>
    </div>`).join('');
}

function loadChat(id) {
  const chats = loadStoredChats();
  const chat = chats.find(c => c.id === id);
  if (!chat) return;
  saveCurrentChat();
  conversationHistory = chat.messages;
  closeHistory();
  // Re-render messages
  const msgs = $('chat-messages');
  msgs.innerHTML = '';
  conversationHistory.forEach(m => {
    if (m.role === 'user') appendUserBubble(m.content, null);
    else {
      const c = appendAssistantBubble();
      c.innerHTML = renderMarkdown(escHtml(m.content));
    }
  });
}

function deleteChat(evt, id) {
  evt.stopPropagation();
  const chats = loadStoredChats().filter(c => c.id !== id);
  localStorage.setItem(HISTORY_KEY, JSON.stringify(chats));
  renderHistoryList();
}

function openHistory() {
  renderHistoryList();
  $('history-panel').classList.remove('hidden');
  $('history-overlay').classList.remove('hidden');
}

function closeHistory() {
  $('history-panel').classList.add('hidden');
  $('history-overlay').classList.add('hidden');
}

$('history-btn').addEventListener('click', openHistory);
$('history-close-btn').addEventListener('click', closeHistory);
$('history-overlay').addEventListener('click', closeHistory);

/* ── New chat ── */
function newChat() {
  saveCurrentChat();
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

/* ── Drag & drop ── */
const chatMsgs = $('chat-messages');
chatMsgs.addEventListener('dragover', e => {
  e.preventDefault();
  chatMsgs.classList.add('drag-over');
});
chatMsgs.addEventListener('dragleave', () => chatMsgs.classList.remove('drag-over'));
chatMsgs.addEventListener('drop', e => {
  e.preventDefault();
  chatMsgs.classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (!file) return;
  attachedFile = file;
  showAttachPreview(file);
});

/* ── Export conversation ── */
function exportConversation() {
  if (!conversationHistory.length) { showToast('No conversation to export', 'err'); return; }
  const lines = conversationHistory.map(m =>
    `## ${m.role === 'user' ? '👤 You' : '🤖 Assistant'}\n\n${m.content}`
  );
  const md = `# AI Agent Conversation\n_Exported ${new Date().toLocaleString()}_\n\n` + lines.join('\n\n---\n\n');
  const blob = new Blob([md], { type: 'text/markdown' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `chat-${Date.now()}.md`;
  a.click();
  showToast('Conversation exported', 'ok');
}
$('export-btn').addEventListener('click', exportConversation);

/* ── File explorer ── */
function openExplorer() {
  $('explorer-panel').classList.remove('hidden');
  $('explorer-overlay').classList.remove('hidden');
  loadFileTree();
}
function closeExplorer() {
  $('explorer-panel').classList.add('hidden');
  $('explorer-overlay').classList.add('hidden');
}
async function loadFileTree() {
  const tree = $('explorer-tree');
  tree.textContent = 'Loading…';
  try {
    const r = await fetch('/api/files/tree', { headers: getAuthHeader() });
    const data = await r.json();
    tree.innerHTML = renderTree(data.tree || []);
  } catch { tree.textContent = 'Failed to load'; }
}
function renderTree(items, depth = 0) {
  return items.map(item => {
    const icon = item.type === 'dir' ? '📁' : getFileIcon(item.name);
    const children = item.children?.length
      ? `<div class="tree-children">${renderTree(item.children, depth + 1)}</div>` : '';
    const onclick = item.type === 'file'
      ? `onclick="readFileIntoChat('${item.path.replace(/'/g, "\\'")}')"`
      : `onclick="this.nextElementSibling?.classList.toggle('hidden')"`;
    return `<div class="tree-item ${item.type}" ${onclick}>
      <span class="tree-icon">${icon}</span>
      <span>${escHtml(item.name)}</span>
    </div>${children ? `<div class="tree-children">${renderTree(item.children || [], depth+1)}</div>` : ''}`;
  }).join('');
}
function getFileIcon(name) {
  const ext = name.split('.').pop().toLowerCase();
  const icons = { py:'🐍', js:'🟨', ts:'🔷', json:'📋', md:'📝', txt:'📄', html:'🌐', css:'🎨', sh:'⚙️', yml:'⚙️', yaml:'⚙️', pdf:'📕', csv:'📊', png:'🖼️', jpg:'🖼️', jpeg:'🖼️' };
  return icons[ext] || '📄';
}
async function readFileIntoChat(path) {
  closeExplorer();
  $('unified-input').value = `Read the file: ${path}`;
  sendSmartMessage();
}
$('explorer-btn').addEventListener('click', openExplorer);
$('explorer-close-btn').addEventListener('click', closeExplorer);
$('explorer-overlay').addEventListener('click', closeExplorer);

/* ── Terminal panel ── */
function openTerminal() {
  $('terminal-panel').classList.remove('hidden');
  $('terminal-input').focus();
}
function closeTerminal() {
  $('terminal-panel').classList.add('hidden');
}
function termPrint(text, cls = 't-out') {
  const out = $('terminal-output');
  const el = document.createElement('span');
  el.className = cls;
  el.textContent = text;
  out.appendChild(el);
  out.appendChild(document.createElement('br'));
  out.scrollTop = out.scrollHeight;
}
async function runTerminalCommand() {
  const cmd = $('terminal-input').value.trim();
  if (!cmd) return;
  $('terminal-input').value = '';
  termPrint(`$ ${cmd}`, 't-cmd');
  try {
    const r = await fetch('/api/task/run', {
      method: 'POST',
      headers: { ...getAuthHeader(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ task: `execute_bash: ${cmd}`, direct_bash: cmd }),
    });
    // Try to execute via bash directly through the smart stream
    const fd = new FormData();
    fd.append('message', `Run this bash command and show me the output: \`${cmd}\``);
    fd.append('history', '[]');
    const res = await fetch('/api/smart/stream', { method:'POST', headers: getAuthHeader(), body: fd });
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let output = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      for (const line of decoder.decode(value).split('\n')) {
        if (!line.startsWith('data: ')) continue;
        const payload = line.slice(6).trim();
        if (payload === '[DONE]') break;
        try {
          const evt = JSON.parse(payload);
          if (evt.type === 'text') output += evt.content;
        } catch {}
      }
    }
    termPrint(output.trim() || '(no output)', 't-out');
  } catch(e) {
    termPrint(`Error: ${e.message}`, 't-err');
  }
}
$('terminal-btn').addEventListener('click', openTerminal);
$('terminal-close-btn').addEventListener('click', closeTerminal);
$('terminal-run-btn').addEventListener('click', runTerminalCommand);
$('terminal-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') runTerminalCommand();
  if (e.key === 'Escape') closeTerminal();
});
$('terminal-clear-btn').addEventListener('click', () => { $('terminal-output').innerHTML = ''; });

/* ── Command palette (Ctrl+K) ── */
const COMMANDS = [
  { icon: '✏️', label: 'New Chat', shortcut: 'Ctrl+N', action: () => newChat() },
  { icon: '🕐', label: 'Chat History', shortcut: '', action: () => openHistory() },
  { icon: '⬇️', label: 'Export Conversation', shortcut: '', action: () => exportConversation() },
  { icon: '📁', label: 'File Explorer', shortcut: '', action: () => openExplorer() },
  { icon: '⚡', label: 'Terminal', shortcut: '', action: () => openTerminal() },
  { icon: '🔍', label: 'Search the web…', shortcut: '', action: () => cmdPrompt('Search the web for: ') },
  { icon: '📸', label: 'Screenshot a URL…', shortcut: '', action: () => cmdPrompt('Take a screenshot of: ') },
  { icon: '🐍', label: 'Run Python code', shortcut: '', action: () => cmdPrompt('Write and run Python code to: ') },
  { icon: '📂', label: 'List project files', shortcut: '', action: () => chipSend('List all files in the current directory') },
  { icon: '🔎', label: 'Analyze project structure', shortcut: '', action: () => chipSend('Summarize the project structure') },
];

let cmdActiveIdx = 0;

function cmdPrompt(prefix) {
  closeCmdPalette();
  $('unified-input').value = prefix;
  $('unified-input').focus();
}

function openCmdPalette() {
  $('cmd-overlay').classList.remove('hidden');
  $('cmd-input').value = '';
  renderCmdList(COMMANDS);
  $('cmd-input').focus();
  cmdActiveIdx = 0;
}

function closeCmdPalette() {
  $('cmd-overlay').classList.add('hidden');
}

function renderCmdList(cmds) {
  $('cmd-list').innerHTML = cmds.map((c, i) => `
    <div class="cmd-item ${i === cmdActiveIdx ? 'active' : ''}" data-idx="${i}">
      <span class="cmd-icon">${c.icon}</span>
      <span class="cmd-label">${escHtml(c.label)}</span>
      ${c.shortcut ? `<span class="cmd-shortcut">${c.shortcut}</span>` : ''}
    </div>`).join('');
  $('cmd-list').querySelectorAll('.cmd-item').forEach((el, i) => {
    el.addEventListener('click', () => { cmds[i].action(); closeCmdPalette(); });
  });
}

$('cmd-input').addEventListener('input', () => {
  const q = $('cmd-input').value.toLowerCase();
  const filtered = COMMANDS.filter(c => c.label.toLowerCase().includes(q));
  cmdActiveIdx = 0;
  renderCmdList(filtered);
});

$('cmd-input').addEventListener('keydown', e => {
  const items = $('cmd-list').querySelectorAll('.cmd-item');
  if (e.key === 'ArrowDown') { e.preventDefault(); cmdActiveIdx = Math.min(cmdActiveIdx + 1, items.length - 1); items.forEach((el,i) => el.classList.toggle('active', i === cmdActiveIdx)); }
  if (e.key === 'ArrowUp') { e.preventDefault(); cmdActiveIdx = Math.max(cmdActiveIdx - 1, 0); items.forEach((el,i) => el.classList.toggle('active', i === cmdActiveIdx)); }
  if (e.key === 'Enter') { e.preventDefault(); items[cmdActiveIdx]?.click(); }
  if (e.key === 'Escape') closeCmdPalette();
});

$('cmd-overlay').addEventListener('click', e => { if (e.target === $('cmd-overlay')) closeCmdPalette(); });

document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') { e.preventDefault(); openCmdPalette(); }
  if ((e.ctrlKey || e.metaKey) && e.key === 'n') { e.preventDefault(); newChat(); }
});

$('unified-send-btn').addEventListener('click', sendSmartMessage);
$('unified-input').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendSmartMessage(); }
});
$('unified-input').addEventListener('input', function () {
  this.style.height = 'auto';
  this.style.height = Math.min(this.scrollHeight, 200) + 'px';
});
