async function api(path, method = 'GET', body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (e) {}
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

function escapeHtml(s) {
  return (s || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function renderJobRow(j) {
  const pct = j.total ? Math.min(100, Math.round((j.progress / j.total) * 100)) : (j.status.startsWith('completed') ? 100 : 0);
  const canRetry = ['failed', 'completed_with_errors', 'cancelled'].includes(j.status) && (j.job_type === 'download' || j.job_type === 'forward');
  return `
    <div class="job-row">
      <div class="job-top">
        <span><strong>#${j.id}</strong> ${j.job_type} — ${escapeHtml(j.dialog_name || j.dialog_id)}</span>
        <span class="status-pill status-${j.status}">${j.status.replace('_', ' ')}</span>
      </div>
      <div class="progress-bar"><div class="progress-fill" style="width:${pct}%"></div></div>
      <div class="muted" style="margin-top:.3rem">${j.progress}/${j.total || '?'}${j.failed_count ? ` • ${j.failed_count} failed` : ''} ${j.output_path ? '• ' + escapeHtml(j.output_path) : ''}${j.error ? ' • ' + escapeHtml(j.error) : ''}</div>
      <div style="display:flex;gap:.5rem">
        ${(j.status === 'pending' || j.status === 'running') ? `<button class="secondary" style="margin-top:.5rem" onclick="cancelJob(${j.id})">Cancel</button>` : ''}
        ${canRetry ? `<button class="secondary" style="margin-top:.5rem" onclick="retryJob(${j.id})">Retry</button>` : ''}
      </div>
    </div>`;
}

async function cancelJob(id) {
  await api(`/api/jobs/${id}/cancel`, 'POST');
  if (typeof refresh === 'function') refresh();
}

async function retryJob(id) {
  await api(`/api/jobs/${id}/retry`, 'POST');
  if (typeof refresh === 'function') refresh();
}

(async () => {
  const badge = document.getElementById('auth-badge');
  if (!badge) return;
  try {
    const status = await api('/api/auth/status');
    if (status.logged_in) {
      badge.innerHTML = `${escapeHtml(status.first_name || status.phone)} · <a href="#" onclick="logout()">logout</a>`;
    } else {
      badge.innerHTML = `<a href="/login">Sign in</a>`;
    }
  } catch (e) { badge.textContent = ''; }
})();

async function logout() {
  await api('/api/auth/logout', 'POST');
  window.location.href = '/login';
}

// ---------- Chat sidebar (global — markup lives in base.html) ----------
let activeChatDialog = null;
let chatPollTimer = null;

const URL_RE = /(https?:\/\/[^\s<]+)/g;
function linkify(escapedText) {
  return escapedText.replace(URL_RE, url => `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`);
}

function renderMediaBlock(m, mediaUrl) {
  if (!m.has_media) return '';
  const kind = m.media_kind;
  if (kind === 'photo') {
    return `<img class="chat-media-img" src="${mediaUrl}" loading="lazy" alt="photo">`;
  }
  if (kind === 'video') {
    return `<video class="chat-media-video" src="${mediaUrl}" controls preload="none"></video>`;
  }
  if (kind === 'voice') {
    return `<audio class="chat-media-audio" src="${mediaUrl}" controls preload="none"></audio>`;
  }
  if (kind === 'audio') {
    return `<audio class="chat-media-audio" src="${mediaUrl}" controls preload="none"></audio>
            <div class="chat-file-name">${escapeHtml(m.file_name || 'audio')}</div>`;
  }
  return `<a class="chat-file-link" href="${mediaUrl}" target="_blank" rel="noopener noreferrer">📎 ${escapeHtml(m.file_name || 'Download file')}</a>`;
}

function openChatSidebar(dialog) {
  const sidebar = document.getElementById('chat-sidebar');
  if (!sidebar) return; // sidebar markup only present via base.html
  activeChatDialog = dialog;
  document.getElementById('chat-title').textContent = dialog.name;
  document.getElementById('chat-messages').innerHTML = 'Loading…';
  sidebar.classList.add('open');
  document.getElementById('chat-backdrop').classList.add('open');
  loadChatMessages();
  if (chatPollTimer) clearInterval(chatPollTimer);
  chatPollTimer = setInterval(loadChatMessages, 4000);
}

function closeChatSidebar() {
  const sidebar = document.getElementById('chat-sidebar');
  if (!sidebar) return;
  sidebar.classList.remove('open');
  document.getElementById('chat-backdrop').classList.remove('open');
  if (chatPollTimer) { clearInterval(chatPollTimer); chatPollTimer = null; }
  activeChatDialog = null;
}

async function loadChatMessages() {
  if (!activeChatDialog) return;
  try {
    const msgs = await api(`/api/dialogs/${activeChatDialog.entity_id}/messages?limit=50`);
    const el = document.getElementById('chat-messages');
    el.innerHTML = msgs.slice().reverse().map(m => {
      const mediaUrl = m.has_media ? `/api/dialogs/${activeChatDialog.entity_id}/messages/${m.id}/media` : null;
      const textHtml = m.text ? linkify(escapeHtml(m.text)) : '';
      return `
      <div class="chat-bubble ${m.out ? 'out' : 'in'}">
        ${!m.out && m.sender_name ? `<div class="chat-sender">${escapeHtml(m.sender_name)}</div>` : ''}
        ${m.forwarded_from ? `<div class="chat-fwd-tag">↪ Forwarded from ${escapeHtml(m.forwarded_from)}</div>` : ''}
        ${renderMediaBlock(m, mediaUrl)}
        ${textHtml ? `<div class="chat-text">${textHtml}</div>` : ''}
        <div class="chat-time">${m.date ? new Date(m.date).toLocaleString() : ''}</div>
      </div>`;
    }).join('') || '<p class="muted">No messages yet.</p>';
    el.scrollTop = el.scrollHeight;
  } catch (e) {
    document.getElementById('chat-messages').innerHTML = `<p class="msg error">${escapeHtml(e.message)}</p>`;
  }
}

async function sendChatMessage(ev) {
  ev.preventDefault();
  const input = document.getElementById('chat-input');
  const text = input.value.trim();
  if (!text || !activeChatDialog) return false;
  input.value = '';
  try {
    await api(`/api/dialogs/${activeChatDialog.entity_id}/messages`, 'POST', {text});
    loadChatMessages();
  } catch (e) {
    alert(e.message);
  }
  return false;
}
