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
  const pct = j.total ? Math.min(100, Math.round((j.progress / j.total) * 100)) : (j.status === 'completed' ? 100 : 0);
  return `
    <div class="job-row">
      <div class="job-top">
        <span><strong>#${j.id}</strong> ${j.job_type} — ${escapeHtml(j.dialog_name || j.dialog_id)}</span>
        <span class="status-pill status-${j.status}">${j.status}</span>
      </div>
      <div class="progress-bar"><div class="progress-fill" style="width:${pct}%"></div></div>
      <div class="muted" style="margin-top:.3rem">${j.progress}/${j.total || '?'} ${j.output_path ? '• ' + escapeHtml(j.output_path) : ''}${j.error ? ' • ' + escapeHtml(j.error) : ''}</div>
      ${(j.status === 'pending' || j.status === 'running') ? `<button class="secondary" style="margin-top:.5rem" onclick="cancelJob(${j.id})">Cancel</button>` : ''}
    </div>`;
}

async function cancelJob(id) {
  await api(`/api/jobs/${id}/cancel`, 'POST');
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
