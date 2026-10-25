import { fetchTemplate, fetchTemplateList, setSelectedSlug } from './templates/store.js';
import { prepareBackgroundImage, renderTemplate } from './templates/engine.js';
import { getSampleArt } from './templates/sample-art.js';
import { loadFonts, templateFontFamilies } from './fonts.js';

const PREVIEW_DATA = {
  artists: ['Phoebe Bridgers', 'Tame Impala', 'Radiohead', 'Fleetwood Mac', 'Kendrick Lamar'],
  tracks: ['Motion Sickness', 'The Less I Know the Better', 'Weird Fishes', 'Dreams', 'Money Trees'],
  minutes: '48,213',
  genre: 'Indie Rock',
};
const SKELETON_COUNT = 6;
const SEARCH_DELAY = 150;

const grid = document.getElementById('template-grid');
const emptyEl = document.getElementById('template-empty');
const searchInput = document.getElementById('template-search');
const categoriesEl = document.getElementById('template-categories');
const sortTabs = Array.from(document.querySelectorAll('[data-sort]'));

const state = {
  list: [],
  catalog: new Map(),
  search: '',
  category: 'all',
  sort: 'featured',
  loading: false,
};

const cardCache = new Map();
let searchTimer = null;

if (emptyEl && grid && grid.contains(emptyEl)) {
  grid.after(emptyEl);
}

function setText(el, text) {
  if (el) {
    el.textContent = text;
  }
}

function el(tag, className) {
  const node = document.createElement(tag);
  if (className) {
    node.className = className;
  }
  return node;
}

function getCategories(list) {
  const set = new Set();
  list.forEach((template) => {
    const meta = template.meta || {};
    if (meta.category) {
      set.add(meta.category);
    }
  });
  return Array.from(set).sort();
}

function renderCategories() {
  if (!categoriesEl) {
    return;
  }
  categoriesEl.innerHTML = '';
  const chip = (value, label, active) => {
    const button = el('button', 'marketplace-category');
    button.type = 'button';
    button.dataset.category = value;
    button.classList.toggle('is-active', active);
    button.setAttribute('aria-pressed', String(active));
    setText(button, label);
    button.addEventListener('click', () => {
      state.category = value;
      renderCategories();
      renderGrid();
    });
    categoriesEl.appendChild(button);
  };
  chip('all', 'all', state.category === 'all');
  getCategories(state.list).forEach((category) => {
    chip(category, category, state.category === category);
  });
}

function createdAt(template) {
  const entry = state.catalog.get(template.slug);
  return template.created_at || (entry && entry.created_at) || '';
}

function filteredAndSorted() {
  let items = state.list.slice();
  const query = state.search.trim().toLowerCase();
  if (query) {
    items = items.filter((template) => {
      const name = (template.name || '').toLowerCase();
      const creator = (template.creator || {}).name || '';
      const tags = Array.isArray(template.meta && template.meta.tags) ? template.meta.tags.join(' ').toLowerCase() : '';
      return name.includes(query) || creator.toLowerCase().includes(query) || tags.includes(query);
    });
  }
  if (state.category !== 'all') {
    items = items.filter((template) => (template.meta || {}).category === state.category);
  }
  const byName = (a, b) => String(a.name).localeCompare(String(b.name));
  if (state.sort === 'featured') {
    items.sort((a, b) => {
      const fa = Boolean(a.meta && a.meta.featured);
      const fb = Boolean(b.meta && b.meta.featured);
      if (fa !== fb) {
        return fa ? -1 : 1;
      }
      return byName(a, b);
    });
  } else if (state.sort === 'popular') {
    items.sort((a, b) => Number(b.uses || 0) - Number(a.uses || 0) || byName(a, b));
  } else {
    items.sort((a, b) => createdAt(b).localeCompare(createdAt(a)) || byName(a, b));
  }
  return items;
}

function renderCanvasPreview(previewWrap, template) {
  const canvas = document.createElement('canvas');
  canvas.setAttribute('role', 'img');
  canvas.setAttribute('aria-label', `${template.name} preview`);
  previewWrap.replaceChildren(canvas);
  fetchTemplate(template.slug)
    .then((fullTemplate) => new Promise((resolve) => {
      const ctx = canvas.getContext('2d');
      canvas.width = fullTemplate.canvas.width;
      canvas.height = fullTemplate.canvas.height;
      prepareBackgroundImage(fullTemplate, () => {
        Promise.all([loadFonts(templateFontFamilies(fullTemplate)), getSampleArt()]).then(([, art]) => {
          renderTemplate(ctx, fullTemplate, { data: PREVIEW_DATA, art, artTransform: {} });
          resolve();
        });
      }, () => resolve());
    }))
    .catch((error) => console.warn('preview failed for', template.slug, error));
}

function previewUrl(slug) {
  const params = new URLSearchParams({ size: 'md' });
  const entry = state.catalog.get(slug);
  if (entry && entry.version) {
    params.set('v', entry.version);
  }
  return `/api/v1/templates/${encodeURIComponent(slug)}/preview.png?${params}`;
}

function renderPreview(previewWrap, template) {
  const img = document.createElement('img');
  img.alt = `${template.name} preview`;
  img.loading = 'lazy';
  img.decoding = 'async';
  img.width = 540;
  img.height = 960;
  img.style.display = 'block';
  img.style.width = '100%';
  img.style.height = '100%';
  img.style.objectFit = 'cover';
  img.addEventListener('error', () => renderCanvasPreview(previewWrap, template), { once: true });
  img.src = previewUrl(template.slug);
  previewWrap.appendChild(img);
}

function makeCard(template) {
  const card = el('article', 'template-card');
  const meta = template.meta || {};
  const creator = template.creator || {};

  const previewWrap = el('div', 'template-card__preview');
  renderPreview(previewWrap, template);

  const body = el('div', 'template-card__body');
  const heading = el('div', 'template-card__heading');
  const title = el('h2', 'template-card__name');
  setText(title, template.name);
  heading.appendChild(title);
  const origin = el('span', `template-card__badge template-card__badge--${template.origin}`);
  setText(origin, template.origin);
  heading.appendChild(origin);
  if (meta.featured) {
    const featured = el('span', 'template-card__badge template-card__badge--featured');
    setText(featured, 'featured');
    heading.appendChild(featured);
  }

  const byline = el('div', 'template-card__byline');
  const avatar = el('span', 'template-card__avatar');
  avatar.setAttribute('aria-hidden', 'true');
  setText(avatar, (creator.name || '?').slice(0, 1).toUpperCase());
  const who = el('span', 'template-card__who');
  const byText = el('span', 'template-card__creator');
  setText(byText, creator.name || 'Unknown');
  const idText = el('span', 'template-card__id');
  setText(idText, `@${(creator.id || '').slice(0, 10)}`);
  who.appendChild(byText);
  who.appendChild(idText);
  byline.appendChild(avatar);
  byline.appendChild(who);

  const footer = el('div', 'template-card__footer');
  const category = el('span', 'template-card__category');
  setText(category, meta.category || 'abstract');
  const uses = el('span', 'template-card__uses');
  const useCount = Number(template.uses || 0);
  setText(uses, `${useCount.toLocaleString()} ${useCount === 1 ? 'use' : 'uses'}`);
  footer.appendChild(category);
  footer.appendChild(uses);

  body.appendChild(heading);
  body.appendChild(byline);
  body.appendChild(footer);

  const useBtn = el('button', 'btn btn--ghost template-card__use');
  useBtn.type = 'button';
  setText(useBtn, 'use this template');
  useBtn.setAttribute('aria-label', `use the ${template.name} template`);
  useBtn.addEventListener('click', () => {
    setSelectedSlug(template.slug);
    fetch(`/api/templates/${encodeURIComponent(template.slug)}/use`, { method: 'POST', keepalive: true }).catch(() => {});
    window.location.href = `/?template=${encodeURIComponent(template.slug)}`;
  });
  body.appendChild(useBtn);

  card.appendChild(previewWrap);
  card.appendChild(body);
  return card;
}

function cardFor(template) {
  let card = cardCache.get(template.slug);
  if (!card) {
    card = makeCard(template);
    cardCache.set(template.slug, card);
  }
  return card;
}

function showMessage(text, actionLabel, onAction) {
  if (!emptyEl) {
    return;
  }
  const message = el('span', 'marketplace-empty__text');
  setText(message, text);
  const nodes = [message];
  if (actionLabel) {
    const button = el('button', 'btn btn--ghost marketplace-empty__action');
    button.type = 'button';
    setText(button, actionLabel);
    button.addEventListener('click', onAction);
    nodes.push(document.createTextNode(' '), button);
  }
  emptyEl.replaceChildren(...nodes);
  emptyEl.hidden = false;
}

function hideMessage() {
  if (emptyEl) {
    emptyEl.hidden = true;
  }
}

function clearFilters() {
  window.clearTimeout(searchTimer);
  state.search = '';
  state.category = 'all';
  if (searchInput) {
    searchInput.value = '';
  }
  renderCategories();
  renderGrid();
  if (searchInput) {
    searchInput.focus();
  }
}

function renderGrid() {
  if (state.loading) {
    return;
  }
  const items = filteredAndSorted();
  grid.replaceChildren(...items.map(cardFor));
  if (items.length) {
    hideMessage();
    return;
  }
  if (!state.list.length) {
    showMessage('no templates yet. be the first to make one.');
    return;
  }
  const query = state.search.trim();
  const filtered = query || state.category !== 'all';
  let text = 'nothing matches those filters.';
  if (query && state.category !== 'all') {
    text = `nothing in ${state.category} matches "${query}".`;
  } else if (query) {
    text = `nothing matches "${query}".`;
  } else if (state.category !== 'all') {
    text = `nothing in ${state.category} yet.`;
  }
  showMessage(text, filtered ? 'clear filters' : '', clearFilters);
}

function renderSkeletons() {
  const cards = [];
  for (let index = 0; index < SKELETON_COUNT; index += 1) {
    const card = el('article', 'template-card template-card--skeleton');
    card.setAttribute('aria-hidden', 'true');
    const body = el('div', 'template-card__body');
    body.append(el('span'), el('span'), el('span'));
    card.appendChild(el('div', 'template-card__preview'));
    card.appendChild(body);
    cards.push(card);
  }
  grid.replaceChildren(...cards);
}

function renderSortTabs() {
  sortTabs.forEach((tab) => {
    const active = tab.dataset.sort === state.sort;
    tab.classList.toggle('is-active', active);
    tab.setAttribute('aria-pressed', String(active));
  });
}

async function fetchCatalog() {
  const catalog = new Map();
  let cursor = null;
  try {
    for (let page = 0; page < 10; page += 1) {
      const params = new URLSearchParams({ limit: '50' });
      if (cursor) {
        params.set('cursor', cursor);
      }
      const response = await fetch(`/api/v1/templates?${params}`);
      if (!response.ok) {
        break;
      }
      const body = await response.json();
      (body.templates || []).forEach((entry) => {
        if (entry && entry.slug) {
          catalog.set(entry.slug, { version: entry.version || '', created_at: entry.created_at || '' });
        }
      });
      cursor = body.page && body.page.has_more ? body.page.next_cursor : null;
      if (!cursor) {
        break;
      }
    }
  } catch (error) {
    console.warn('Unable to load template catalog details', error);
  }
  return catalog;
}

async function load() {
  state.loading = true;
  hideMessage();
  grid.setAttribute('aria-busy', 'true');
  renderSkeletons();
  try {
    const [list, catalog] = await Promise.all([fetchTemplateList(), fetchCatalog()]);
    state.list = list;
    state.catalog = catalog;
    state.loading = false;
    renderCategories();
    renderGrid();
  } catch (error) {
    console.warn('Unable to load template list', error);
    state.loading = false;
    grid.replaceChildren();
    showMessage('couldn\'t load templates.', 'retry', load);
  } finally {
    grid.setAttribute('aria-busy', 'false');
  }
}

if (searchInput) {
  searchInput.addEventListener('input', () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => {
      state.search = searchInput.value;
      renderGrid();
    }, SEARCH_DELAY);
  });
}

sortTabs.forEach((tab) => {
  tab.addEventListener('click', () => {
    state.sort = tab.dataset.sort;
    renderSortTabs();
    renderGrid();
  });
});

renderSortTabs();
load();
