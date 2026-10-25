import { normaliseTemplate, prepareBackgroundImage, renderTemplate } from './templates/engine.js';
import { getSampleData } from './templates/sample-data.js';
import { getSampleArt } from './templates/sample-art.js';
import { loadFonts, templateFontFamilies } from './fonts.js';

const keyInput = document.getElementById('admin-key');
const connectBtn = document.getElementById('admin-connect');
const refreshBtn = document.getElementById('admin-refresh');
const statusEl = document.getElementById('admin-status');
const listEl = document.getElementById('admin-list');
const emptyEl = document.getElementById('admin-empty');
const KEY_STORAGE = 'wrappedReviewKey';
const PREVIEW_SAMPLE = 'indie-night';

if (emptyEl && listEl && listEl.contains(emptyEl)) {
  listEl.after(emptyEl);
}

function getKey() {
  try {
    return sessionStorage.getItem(KEY_STORAGE) || '';
  } catch (error) {
    return '';
  }
}

function setKey(key) {
  try {
    sessionStorage.setItem(KEY_STORAGE, key);
  } catch (error) {}
}

function clearKey() {
  try {
    sessionStorage.removeItem(KEY_STORAGE);
  } catch (error) {}
}

class UnauthorizedError extends Error {}

function handleUnauthorized() {
  clearKey();
  keyInput.value = '';
  refreshBtn.hidden = true;
  listEl.innerHTML = '';
  if (emptyEl) {
    emptyEl.hidden = false;
  }
  setStatus('that key didn\'t work. paste it again.', 'error');
  keyInput.focus();
}

async function ensureOk(response) {
  if (response.status === 401) {
    throw new UnauthorizedError(await parseError(response));
  }
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return response;
}

function setStatus(message, tone = 'info') {
  if (!message) {
    statusEl.hidden = true;
    statusEl.textContent = '';
    return;
  }
  statusEl.hidden = false;
  statusEl.textContent = message;
  statusEl.dataset.tone = tone;
}

async function parseError(response) {
  const fallback = `Request failed (${response.status})`;
  const contentType = response.headers.get('content-type') || '';
  try {
    if (contentType.includes('application/json')) {
      const body = await response.json();
      return body.description || body.error || fallback;
    }
    const text = await response.text();
    return text.replace(/<[^>]+>/g, '').trim() || fallback;
  } catch (error) {
    return fallback;
  }
}

async function review(action, submissionId) {
  const response = await fetch('/api/templates/review', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${getKey()}`,
    },
    body: JSON.stringify({ action, submission_id: submissionId }),
  });
  await ensureOk(response);
  return response.json();
}

function renderSubmission(card, submission) {
  const template = normaliseTemplate(submission.template);
  const sample = getSampleData(PREVIEW_SAMPLE);
  const canvas = card.querySelector('.admin-card__preview canvas');
  const ctx = canvas.getContext('2d');
  canvas.width = template.canvas.width;
  canvas.height = template.canvas.height;
  prepareBackgroundImage(template, () => {
    loadFonts(templateFontFamilies(template)).then(() => {
      getSampleArt().then((art) => {
        renderTemplate(ctx, template, { data: sample.data, art, artTransform: {} });
      });
    });
  }, () => {});
}

function makeCard(submission) {
  const card = document.createElement('article');
  card.className = 'admin-card';
  const template = submission.template || {};

  const preview = document.createElement('div');
  preview.className = 'admin-card__preview';
  const canvas = document.createElement('canvas');
  canvas.setAttribute('role', 'img');
  canvas.setAttribute('aria-label', `${template.name || 'untitled'} preview`);
  preview.appendChild(canvas);

  const body = document.createElement('div');
  body.className = 'admin-card__body';
  const title = document.createElement('h2');
  title.className = 'admin-card__name';
  title.textContent = template.name || 'Untitled';
  body.appendChild(title);

  const meta = document.createElement('p');
  meta.className = 'admin-card__meta';
  const creator = submission.creator || {};
  meta.textContent = `${creator.name || 'Unknown'} · @${(creator.id || '').slice(0, 12)} · ${template.slug} · ${submission.created_at || ''}`;
  body.appendChild(meta);

  const actions = document.createElement('div');
  actions.className = 'admin-card__actions';
  const approve = document.createElement('button');
  approve.type = 'button';
  approve.className = 'btn';
  approve.textContent = 'approve';
  approve.addEventListener('click', async () => {
    approve.disabled = true;
    try {
      await review('approve', submission.submission_id);
      card.remove();
      markEmpty();
      setStatus('approved! it\'s live in the library now.', 'success');
    } catch (error) {
      if (error instanceof UnauthorizedError) {
        handleUnauthorized();
        return;
      }
      setStatus(error.message || 'approve failed.', 'error');
    } finally {
      approve.disabled = false;
    }
  });
  const reject = document.createElement('button');
  reject.type = 'button';
  reject.className = 'btn btn--ghost';
  reject.textContent = 'reject';
  reject.addEventListener('click', async () => {
    reject.disabled = true;
    try {
      await review('reject', submission.submission_id);
      card.remove();
      markEmpty();
      setStatus('rejected. gone, nothing to see.', 'info');
    } catch (error) {
      if (error instanceof UnauthorizedError) {
        handleUnauthorized();
        return;
      }
      setStatus(error.message || 'reject failed.', 'error');
    } finally {
      reject.disabled = false;
    }
  });
  actions.appendChild(approve);
  actions.appendChild(reject);
  body.appendChild(actions);

  card.appendChild(preview);
  card.appendChild(body);
  return card;
}

function markEmpty() {
  if (emptyEl) {
    emptyEl.hidden = true;
  }
}

async function loadPending() {
  listEl.innerHTML = '';
  try {
    const response = await fetch('/api/templates/review', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${getKey()}`,
      },
      body: JSON.stringify({ action: 'list' }),
    });
    await ensureOk(response);
    const payload = await response.json();
    const pending = Array.isArray(payload.pending) ? payload.pending : [];
    if (emptyEl) {
      emptyEl.hidden = true;
    }
    pending.forEach((submission) => {
      const card = makeCard(submission);
      renderSubmission(card, submission);
      listEl.appendChild(card);
    });
    if (!pending.length) {
      setStatus('queue\'s empty. nothing to review, all clear.', 'success');
    } else {
      setStatus(`${pending.length} submission${pending.length === 1 ? '' : 's'} sitting in the queue.`, 'info');
    }
  } catch (error) {
    if (error instanceof UnauthorizedError) {
      handleUnauthorized();
      return;
    }
    if (emptyEl) {
      emptyEl.hidden = true;
    }
    setStatus(error.message || 'could not load submissions.', 'error');
  }
}

function connect() {
  const key = keyInput.value.trim();
  if (!key) {
    setStatus('need a key first. it\'s in your .env.', 'error');
    return;
  }
  setKey(key);
  refreshBtn.hidden = false;
  loadPending();
}

connectBtn.addEventListener('click', connect);
keyInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.isComposing) {
    event.preventDefault();
    connect();
  }
});

refreshBtn.addEventListener('click', loadPending);

window.addEventListener('load', () => {
  keyInput.value = getKey();
  if (getKey()) {
    refreshBtn.hidden = false;
    loadPending();
  } else if (emptyEl) {
    emptyEl.hidden = false;
  }
});
