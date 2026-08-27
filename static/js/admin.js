import { normaliseTemplate, prepareBackgroundImage, renderTemplate } from './templates/engine.js';
import { getSampleData, SAMPLES } from './templates/sample-data.js';
import { getSampleArt } from './templates/sample-art.js';
import { loadFonts, templateFontFamilies } from './fonts.js';

const keyInput = document.getElementById('admin-key');
const connectBtn = document.getElementById('admin-connect');
const refreshBtn = document.getElementById('admin-refresh');
const statusEl = document.getElementById('admin-status');
const listEl = document.getElementById('admin-list');
const emptyEl = document.getElementById('admin-empty');
const KEY_STORAGE = 'wrappedReviewKey';

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
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return response.json();
}

function renderSubmission(card, submission, index) {
  const template = normaliseTemplate(submission.template);
  const sample = getSampleData(SAMPLES[index % SAMPLES.length].id);
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

function makeCard(submission, index) {
  const card = document.createElement('article');
  card.className = 'admin-card';
  const template = submission.template || {};

  const preview = document.createElement('div');
  preview.className = 'admin-card__preview';
  const canvas = document.createElement('canvas');
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
  const hasCards = listEl.querySelector('.admin-card');
  emptyEl.hidden = Boolean(hasCards);
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
    if (!response.ok) {
      throw new Error(await parseError(response));
    }
    const payload = await response.json();
    const pending = Array.isArray(payload.pending) ? payload.pending : [];
    emptyEl.hidden = Boolean(pending.length);
    pending.forEach((submission, index) => {
      const card = makeCard(submission, index);
      renderSubmission(card, submission, index);
      listEl.appendChild(card);
    });
    if (!pending.length) {
      setStatus('queue\'s empty. nothing to review, all clear.', 'success');
    } else {
      setStatus(`${pending.length} submission${pending.length === 1 ? '' : 's'} sitting in the queue.`, 'info');
    }
  } catch (error) {
    emptyEl.hidden = true;
    setStatus(error.message || 'could not load submissions.', 'error');
  }
}

connectBtn.addEventListener('click', () => {
  const key = keyInput.value.trim();
  if (!key) {
    setStatus('need a key first. it\'s in your .env.', 'error');
    return;
  }
  setKey(key);
  refreshBtn.hidden = false;
  loadPending();
});

refreshBtn.addEventListener('click', loadPending);

window.addEventListener('load', () => {
  keyInput.value = getKey();
  if (getKey()) {
    refreshBtn.hidden = false;
    loadPending();
  }
});
