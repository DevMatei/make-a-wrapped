import { normaliseTemplate } from './engine.js';
import { readLocal, writeLocal, removeLocal } from '../storage.js';

const SELECTED_KEY = 'wrappedTemplateSlug';

let templateListCache = null;
let templateCache = Object.create(null);

async function request(path, options = {}) {
  const response = await fetch(path, { cache: 'no-store', ...options });
  if (!response.ok) {
    throw new Error(`Request failed (${response.status})`);
  }
  return response.json();
}

export async function fetchTemplateList() {
  if (templateListCache) {
    return templateListCache;
  }
  try {
    const payload = await request('/api/templates');
    templateListCache = Array.isArray(payload.templates) ? payload.templates : [];
  } catch (error) {
    console.warn('Unable to load template list', error);
    templateListCache = [];
  }
  return templateListCache;
}

export async function fetchTemplate(slug) {
  const cached = templateCache[slug];
  if (cached) {
    return cached;
  }
  const payload = await request(`/api/templates/${encodeURIComponent(slug)}`);
  const template = normaliseTemplate(payload.template);
  templateCache[slug] = template;
  return template;
}

export function getSelectedSlug() {
  return readLocal(SELECTED_KEY) || 'black';
}

export function setSelectedSlug(slug) {
  if (slug) {
    writeLocal(SELECTED_KEY, slug);
  }
}

export function clearSelectedSlug() {
  removeLocal(SELECTED_KEY);
}

export function getTemplateListCache() {
  return templateListCache || [];
}

export function slugFromLocation() {
  const params = new URLSearchParams(window.location.search);
  return params.get('template') || '';
}

export async function loadSelectedTemplate() {
  const explicit = slugFromLocation();
  const slug = explicit || getSelectedSlug();
  try {
    const template = await fetchTemplate(slug);
    setSelectedSlug(template.slug);
    return { template, slug: template.slug, fromLocation: Boolean(explicit) };
  } catch (error) {
    console.warn('Selected template unavailable, falling back to default', error);
    const fallback = await fetchTemplate('black');
    setSelectedSlug('black');
    return { template: fallback, slug: 'black', fromLocation: false };
  }
}
