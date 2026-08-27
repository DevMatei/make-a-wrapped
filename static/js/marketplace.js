import { fetchTemplate, fetchTemplateList, setSelectedSlug } from './templates/store.js';
import { prepareBackgroundImage, renderTemplate } from './templates/engine.js';
import { SAMPLES, getSampleData } from './templates/sample-data.js';
import { getSampleArt } from './templates/sample-art.js';
import { loadFonts, templateFontFamilies } from './fonts.js';

const grid = document.getElementById('template-grid');
const emptyEl = document.getElementById('template-empty');
const searchInput = document.getElementById('template-search');
const categoriesEl = document.getElementById('template-categories');
const sortTabs = Array.from(document.querySelectorAll('[data-sort]'));

const state = {
  list: [],
  search: '',
  category: 'all',
  sort: 'featured',
  count: 0,
};

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
  categoriesEl.innerHTML = '';
  const chip = (value, label, active) => {
    const button = el('button', 'marketplace-category');
    button.type = 'button';
    button.dataset.category = value;
    button.classList.toggle('is-active', active);
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
  if (state.sort === 'featured') {
    items.sort((a, b) => {
      const fa = Boolean(a.meta && a.meta.featured);
      const fb = Boolean(b.meta && b.meta.featured);
      if (fa !== fb) {
        return fa ? -1 : 1;
      }
      return String(a.name).localeCompare(String(b.name));
    });
  } else if (state.sort === 'popular') {
    items.sort((a, b) => Number(b.uses || 0) - Number(a.uses || 0));
  } else {
    items.sort((a, b) => {
      const ta = a.created_at || '';
      const tb = b.created_at || '';
      return tb.localeCompare(ta);
    });
  }
  return items;
}

function renderPreview(canvas, template, index) {
  const sample = getSampleData(SAMPLES[index % SAMPLES.length].id);
  const ctx = canvas.getContext('2d');
  canvas.width = template.canvas.width;
  canvas.height = template.canvas.height;
  return new Promise((resolve) => {
    prepareBackgroundImage(template, () => {
      loadFonts(templateFontFamilies(template)).then(() => {
        getSampleArt().then((art) => {
          renderTemplate(ctx, template, { data: sample.data, art, artTransform: {} });
          resolve();
        });
      });
    }, () => resolve());
  });
}

function makeCard(template, index) {
  const card = el('article', 'template-card');
  const meta = template.meta || {};
  const creator = template.creator || {};

  const previewWrap = el('div', 'template-card__preview');
  const canvas = document.createElement('canvas');
  previewWrap.appendChild(canvas);
  fetchTemplate(template.slug)
    .then((fullTemplate) => renderPreview(canvas, fullTemplate, index))
    .catch((error) => console.warn('preview failed for', template.slug, error));

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
  setText(uses, `${Number(template.uses || 0)} uses`);
  footer.appendChild(category);
  footer.appendChild(uses);

  body.appendChild(heading);
  body.appendChild(byline);
  body.appendChild(footer);

  const useBtn = el('button', 'btn template-card__use');
  useBtn.type = 'button';
  setText(useBtn, 'use this template');
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

function renderGrid() {
  const items = filteredAndSorted();
  grid.innerHTML = '';
  if (!items.length) {
    emptyEl.hidden = false;
    return;
  }
  emptyEl.hidden = true;
  items.forEach((template, index) => {
    grid.appendChild(makeCard(template, index));
  });
}

function renderSortTabs() {
  sortTabs.forEach((tab) => {
    tab.classList.toggle('is-active', tab.dataset.sort === state.sort);
  });
}

searchInput.addEventListener('input', () => {
  state.search = searchInput.value;
  renderGrid();
});

sortTabs.forEach((tab) => {
  tab.addEventListener('click', () => {
    state.sort = tab.dataset.sort;
    renderSortTabs();
    renderGrid();
  });
});

async function init() {
  const list = await fetchTemplateList();
  state.list = list;
  renderCategories();
  renderSortTabs();
  renderGrid();
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(() => renderGrid());
  }
}

window.addEventListener('load', init);
