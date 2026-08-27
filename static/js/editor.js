import { fontString, fitText, normaliseTemplate, prepareBackgroundImage, renderTemplate, resolveColor, resolveSlotDisplay } from './templates/engine.js';
import { buildCreatorPayload, getCreatorDisplay, getCreatorId, setCreatorDisplay } from './templates/creator.js';
import { fetchTemplate } from './templates/store.js';
import { SAMPLES, getSampleData } from './templates/sample-data.js';
import { getSampleArt } from './templates/sample-art.js';
import { FONT_FAMILIES, FONT_WEIGHTS, loadFonts, templateFontFamilies } from './fonts.js';
import { readFileAsDataUrl } from './utils.js';

const CATEGORIES = ['dark', 'light', 'minimal', 'vibrant', 'retro', 'abstract', 'bold', 'soft'];

const canvas = document.getElementById('editor-canvas');
const nameInput = document.getElementById('editor-name');
const slugInput = document.getElementById('editor-slug');
const categorySelect = document.getElementById('editor-category');
const tagsInput = document.getElementById('editor-tags');
const samplesEl = document.getElementById('editor-samples');
const bgTypeEl = document.getElementById('editor-bg-type');
const bgSolidField = document.getElementById('editor-bg-solid');
const bgGradientField = document.getElementById('editor-bg-gradient');
const bgImageField = document.getElementById('editor-bg-image-field');
const bgAngleField = document.getElementById('editor-bg-angle-field');
const bgColorInput = document.getElementById('editor-bg-color');
const bgColorHex = document.getElementById('editor-bg-color-hex');
const bgColorsEl = document.getElementById('editor-bg-colors');
const bgAngleInput = document.getElementById('editor-bg-angle');
const bgAngleValue = document.getElementById('editor-bg-angle-value');
const bgImageFile = document.getElementById('editor-bg-image-file');
const bgImageHint = document.getElementById('editor-bg-image-hint');
const bgImageUploadBtn = document.querySelector('.editor-uploadbtn');
const paletteLabelInput = document.getElementById('editor-palette-label');
const paletteValueInput = document.getElementById('editor-palette-value');
const artEnabledInput = document.getElementById('editor-art-enabled');
const artFrameInput = document.getElementById('editor-art-frame');
const artXInput = document.getElementById('editor-art-x');
const artYInput = document.getElementById('editor-art-y');
const artSizeInput = document.getElementById('editor-art-size');
const elementsEl = document.getElementById('editor-elements');
const propertiesPanelEl = document.querySelector('.editor-panel--properties');
const propertiesEl = document.getElementById('editor-properties');
const sampleArtPromise = getSampleArt();
const resetBtn = document.getElementById('editor-reset');
const submitBtn = document.getElementById('editor-submit');
const exportBtn = document.getElementById('editor-export');
const importBtn = document.getElementById('editor-import');
const importFileInput = document.getElementById('editor-import-file');
const toastEl = document.getElementById('editor-toast');
const creatorNameInput = document.getElementById('editor-creator-name');
const creatorWebsiteInput = document.getElementById('editor-creator-website');
const creatorBioInput = document.getElementById('editor-creator-bio');
const creatorIdEl = document.getElementById('editor-creator-id');
const headerCopy = document.getElementById('editor-header-copy');

let template = null;
let selectedId = null;
let sampleId = 'indie-night';
let data = getSampleData(sampleId).data;
let sampleArt = null;
let editing = null;
let guides = [];
let bgUploadFile = null;
let bgIsLocal = false;
let slugTouched = false;
let turnstileToken = null;
let turnstileEnabled = false;
let turnstileSiteKey = '';
let turnstileWidgetId = null;
let turnstileWrapper = null;
let turnstileWaiter = null;
let turnstileWaiterResolve = null;

function deepClone(value) {
  return JSON.parse(JSON.stringify(value));
}

function dataForRenderer() {
  return data;
}

function getTemplateElement(id) {
  return (template.elements || []).find((element) => element.id === id) || null;
}

function canvasPoint(event) {
  const rect = canvas.getBoundingClientRect();
  const scaleX = canvas.width / rect.width;
  const scaleY = canvas.height / rect.height;
  return { x: (event.clientX - rect.left) * scaleX, y: (event.clientY - rect.top) * scaleY };
}

function measureBounds(element) {
  const ctx = canvas.getContext('2d');
  ctx.save();
  ctx.font = fontString(element.font || {});
  let width = 0;
  let height = Number.isFinite(element.font && element.font.size) ? element.font.size : 48;
  if (element.kind === 'text') {
    width = ctx.measureText(element.text || '').width;
  } else if (element.kind === 'list') {
    const items = resolveSlotDisplay(data, element.slot);
    const lineHeight = Number.isFinite(element.lineHeight) ? element.lineHeight : 72;
    const maxWidth = Number.isFinite(element.maxWidth) ? element.maxWidth : 0;
    let maxLine = 0;
    items.forEach((item) => {
      const value = typeof item === 'string' ? item : '';
      maxLine = Math.max(maxLine, ctx.measureText(value).width);
    });
    width = Math.min(maxLine, maxWidth || maxLine);
    height = lineHeight * Math.max(items.length, 1);
  } else {
    const value = resolveSlotDisplay(data, element.slot);
    const maxWidth = Number.isFinite(element.maxWidth) ? element.maxWidth : 0;
    const layout = fitText(ctx, value, { font: element.font, maxWidth, minFontSize: element.minFontSize });
    ctx.font = layout.font;
    width = Math.min(ctx.measureText(layout.text).width, maxWidth || ctx.measureText(layout.text).width);
    height = Number.isFinite(element.font && element.font.size) ? element.font.size : 48;
  }
  ctx.restore();
  return { x: element.x, y: element.y, width, height };
}

function artworkBounds() {
  const art = template.artwork || {};
  return { x: art.x, y: art.y, width: art.size, height: art.size };
}

function boundsForSelection(id) {
  if (id === 'artwork') {
    return artworkBounds();
  }
  const element = getTemplateElement(id);
  return element ? measureBounds(element) : null;
}

function hitTest(point) {
  const elements = template.elements || [];
  for (let index = elements.length - 1; index >= 0; index -= 1) {
    const element = elements[index];
    if (element.kind === 'text' && !(element.text || '').trim()) {
      continue;
    }
    const bounds = measureBounds(element);
    if (point.x >= bounds.x && point.x <= bounds.x + bounds.width && point.y >= bounds.y && point.y <= bounds.y + bounds.height) {
      return element.id;
    }
  }
  const art = artworkBounds();
  if (template.artwork && template.artwork.enabled !== false
    && point.x >= art.x && point.x <= art.x + art.width && point.y >= art.y && point.y <= art.y + art.height) {
    return 'artwork';
  }
  return null;
}

function drawSelection(ctx) {
  const bounds = boundsForSelection(selectedId);
  if (!bounds) {
    return;
  }
  ctx.save();
  ctx.strokeStyle = '#c084fc';
  ctx.lineWidth = 3;
  ctx.setLineDash([8, 6]);
  ctx.strokeRect(bounds.x, bounds.y, bounds.width, bounds.height);
  ctx.setLineDash([]);
  const handle = 14;
  ctx.fillStyle = '#c084fc';
  ctx.fillRect(bounds.x + bounds.width - handle, bounds.y + bounds.height - handle, handle, handle);
  ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
  ctx.fillRect(bounds.x + bounds.width - handle - 1, bounds.y + bounds.height - handle - 1, 2, 2);
  ctx.restore();
}

function snapAxis(anchors, targets, tolerance) {
  let best = null;
  anchors.forEach((anchor) => {
    targets.forEach((target) => {
      const dist = Math.abs(anchor - target);
      if (dist <= tolerance && (!best || dist < best.dist)) {
        best = { dist, delta: target - anchor, guide: target };
      }
    });
  });
  return best;
}

function snapBounds(bounds, excludeId) {
  const tolerance = 6;
  const targetsX = [canvas.width / 2];
  const targetsY = [canvas.height / 2];
  const neighbors = [];
  (template.elements || []).forEach((element) => {
    if (element.id !== excludeId) {
      neighbors.push(measureBounds(element));
    }
  });
  if (excludeId !== 'artwork' && template.artwork && template.artwork.enabled !== false) {
    neighbors.push(artworkBounds());
  }
  neighbors.forEach((neighbor) => {
    targetsX.push(neighbor.x, neighbor.x + neighbor.width / 2, neighbor.x + neighbor.width);
    targetsY.push(neighbor.y, neighbor.y + neighbor.height / 2, neighbor.y + neighbor.height);
  });
  const snappedX = snapAxis([bounds.x, bounds.x + bounds.width / 2, bounds.x + bounds.width], targetsX, tolerance);
  const snappedY = snapAxis([bounds.y, bounds.y + bounds.height / 2, bounds.y + bounds.height], targetsY, tolerance);
  const guides = [];
  if (snappedX) {
    bounds.x += snappedX.delta;
    guides.push({ axis: 'x', pos: snappedX.guide });
  }
  if (snappedY) {
    bounds.y += snappedY.delta;
    guides.push({ axis: 'y', pos: snappedY.guide });
  }
  return { bounds, guides };
}

function positionTarget(id, x, y) {
  if (id === 'artwork') {
    template.artwork.x = x;
    template.artwork.y = y;
    return;
  }
  const element = getTemplateElement(id);
  if (element) {
    element.x = x;
    element.y = y;
  }
}

function render() {
  if (!template) {
    return;
  }
  prepareBackgroundImage(template, () => {
    const ctx = canvas.getContext('2d');
    renderTemplate(ctx, template, {
      data: dataForRenderer(),
      art: sampleArt,
      artTransform: {},
    });
    drawGuides(ctx);
    if (selectedId) {
      drawSelection(ctx);
    }
  });
}

function drawGuides(ctx) {
  if (!guides.length) {
    return;
  }
  ctx.save();
  ctx.strokeStyle = '#22d3ee';
  ctx.lineWidth = 1.5;
  ctx.setLineDash([5, 5]);
  guides.forEach((guide) => {
    ctx.beginPath();
    if (guide.axis === 'x') {
      ctx.moveTo(guide.pos, 0);
      ctx.lineTo(guide.pos, canvas.height);
    } else {
      ctx.moveTo(0, guide.pos);
      ctx.lineTo(canvas.width, guide.pos);
    }
    ctx.stroke();
  });
  ctx.restore();
}

function moveLayer(arrayIdx, deltaArray) {
  const elements = template.elements || [];
  const target = arrayIdx + deltaArray;
  if (target < 0 || target >= elements.length) {
    return;
  }
  [elements[arrayIdx], elements[target]] = [elements[target], elements[arrayIdx]];
  renderElementsList();
  render();
}

function renderElementsList() {
  elementsEl.innerHTML = '';
  const elements = template.elements || [];
  const n = elements.length;
  for (let i = n - 1; i >= 0; i -= 1) {
    const element = elements[i];
    const row = document.createElement('li');
    row.className = 'editor-element-row';
    row.classList.toggle('is-selected', element.id === selectedId);
    const swatch = document.createElement('span');
    swatch.className = 'editor-element-row__swatch';
    swatch.style.background = resolveColor(template, element.color);
    row.appendChild(swatch);
    const kindName = element.kind === 'text' ? 'text' : element.kind === 'list' ? 'list' : 'stat';
    const label = document.createElement('span');
    label.className = 'editor-element-row__label';
    label.textContent = element.text || element.slot || element.id;
    row.appendChild(label);
    const type = document.createElement('span');
    type.className = 'editor-element-row__type';
    type.textContent = kindName;
    row.appendChild(type);

    const controls = document.createElement('span');
    controls.className = 'editor-element-row__controls';
    const up = document.createElement('button');
    up.type = 'button';
    up.textContent = '↑';
    up.disabled = i === n - 1;
    up.title = 'bring forward';
    up.addEventListener('click', (event) => {
      event.stopPropagation();
      moveLayer(i, 1);
    });
    const down = document.createElement('button');
    down.type = 'button';
    down.textContent = '↓';
    down.disabled = i === 0;
    down.title = 'send backward';
    down.addEventListener('click', (event) => {
      event.stopPropagation();
      moveLayer(i, -1);
    });
    const del = document.createElement('button');
    del.type = 'button';
    del.textContent = '×';
    del.addEventListener('click', (event) => {
      event.stopPropagation();
      deleteElement(element.id);
    });
    controls.appendChild(up);
    controls.appendChild(down);
    controls.appendChild(del);
    row.appendChild(controls);
    row.addEventListener('click', () => selectElement(element.id));
    elementsEl.appendChild(row);
  }

  const artRow = document.createElement('li');
  artRow.className = 'editor-element-row editor-element-row--art';
  artRow.classList.toggle('is-selected', selectedId === 'artwork');
  const artSwatch = document.createElement('span');
  artSwatch.className = 'editor-element-row__swatch';
  artSwatch.style.background = 'linear-gradient(135deg, #c084fc, #7c3aed)';
  artRow.appendChild(artSwatch);
  const artLabel = document.createElement('span');
  artLabel.className = 'editor-element-row__label';
  artLabel.textContent = 'album art';
  artRow.appendChild(artLabel);
  const artType = document.createElement('span');
  artType.className = 'editor-element-row__type';
  artType.textContent = 'art';
  artRow.appendChild(artType);
  const artCtl = document.createElement('span');
  artCtl.className = 'editor-element-row__controls';
  const artEye = document.createElement('button');
  artEye.type = 'button';
  artEye.textContent = template.artwork && template.artwork.enabled !== false ? '●' : '○';
  artEye.title = 'toggle visibility in the background panel';
  artCtl.appendChild(artEye);
  artRow.appendChild(artCtl);
  artRow.addEventListener('click', () => selectElement('artwork'));
  elementsEl.appendChild(artRow);
}

function deleteElement(id) {
  template.elements = (template.elements || []).filter((element) => element.id !== id);
  if (selectedId === id) {
    selectedId = null;
    renderPropertiesPanel();
  }
  renderElementsList();
  render();
}

function addElement(kind) {
  const elements = template.elements || [];
  const id = `${kind}-${Date.now()}`;
  let element;
  if (kind === 'text') {
    element = { id, kind: 'text', text: 'Heading', x: 112, y: 470, font: { family: 'Nunito', weight: 700, size: 48 }, color: 'label', baseline: 'top', align: 'left' };
  } else if (kind === 'list') {
    element = { id, kind: 'list', slot: 'artists', x: 112, y: 760, font: { family: 'Nunito', weight: 700, size: 45 }, color: 'value', lineHeight: 72, maxWidth: 454, minFontSize: 24, ellipsize: true, prefix: true, baseline: 'top', align: 'left' };
  } else {
    element = { id, kind: 'slot', slot: 'minutes', x: 112, y: 1160, font: { family: 'Nunito', weight: 800, size: 80 }, color: 'value', maxWidth: 454, minFontSize: 44, ellipsize: true, prefix: false, baseline: 'top', align: 'left' };
  }
  elements.push(element);
  template.elements = elements;
  selectElement(id);
  renderElementsList();
  render();
  renderPropertiesPanel();
}

function selectElement(id) {
  selectedId = id;
  renderElementsList();
  renderPropertiesPanel();
  render();
}

function fieldNumber(value, label, onChange) {
  const wrapper = document.createElement('div');
  wrapper.className = 'editor-field';
  const labelEl = document.createElement('label');
  labelEl.className = 'form__label';
  labelEl.textContent = label;
  const input = document.createElement('input');
  input.type = 'number';
  input.step = '1';
  input.value = String(value);
  input.addEventListener('input', () => {
    const parsed = Number(input.value);
    if (Number.isFinite(parsed)) {
      onChange(parsed);
    }
  });
  wrapper.appendChild(labelEl);
  wrapper.appendChild(input);
  return wrapper;
}

function fieldText(value, label, onChange) {
  const wrapper = document.createElement('div');
  wrapper.className = 'editor-field';
  const labelEl = document.createElement('label');
  labelEl.className = 'form__label';
  labelEl.textContent = label;
  const input = document.createElement('input');
  input.type = 'text';
  input.value = value || '';
  input.addEventListener('input', () => onChange(input.value));
  wrapper.appendChild(labelEl);
  wrapper.appendChild(input);
  return wrapper;
}

function fieldSelect(options, value, label, onChange) {
  const wrapper = document.createElement('div');
  wrapper.className = 'editor-field';
  const labelEl = document.createElement('label');
  labelEl.className = 'form__label';
  labelEl.textContent = label;
  const select = document.createElement('select');
  options.forEach((option) => {
    const opt = document.createElement('option');
    opt.value = option.value;
    opt.textContent = option.label;
    if (option.value === value) {
      opt.selected = true;
    }
    select.appendChild(opt);
  });
  select.addEventListener('change', () => onChange(select.value));
  wrapper.appendChild(labelEl);
  wrapper.appendChild(select);
  return wrapper;
}

function fieldToggle(value, label, onChange) {
  const wrapper = document.createElement('label');
  wrapper.className = 'editor-field editor-toggle';
  const input = document.createElement('input');
  input.type = 'checkbox';
  input.checked = Boolean(value);
  input.addEventListener('change', () => onChange(input.checked));
  const text = document.createElement('span');
  text.textContent = label;
  wrapper.appendChild(input);
  wrapper.appendChild(text);
  return wrapper;
}

function fieldColor(value, onChange) {
  const wrapper = document.createElement('div');
  wrapper.className = 'editor-field';
  const labelEl = document.createElement('label');
  labelEl.className = 'form__label';
  labelEl.textContent = 'color';
  wrapper.appendChild(labelEl);
  const row = document.createElement('div');
  row.className = 'editor-color';
  const btnLabel = document.createElement('button');
  btnLabel.type = 'button';
  btnLabel.className = 'editor-color__token';
  btnLabel.textContent = 'label';
  const btnValue = document.createElement('button');
  btnValue.type = 'button';
  btnValue.className = 'editor-color__token';
  btnValue.textContent = 'value';
  const picker = document.createElement('input');
  picker.type = 'color';
  picker.value = /^#[0-9a-f]{6}$/i.test(value) ? value : (template.palette.value || '#ffffff');
  const applyToken = (token) => {
    btnLabel.classList.toggle('is-active', token === 'label');
    btnValue.classList.toggle('is-active', token === 'value');
    picker.classList.toggle('is-visible', !token);
  };
  btnLabel.addEventListener('click', () => { onChange('label'); applyToken('label'); });
  btnValue.addEventListener('click', () => { onChange('value'); applyToken('value'); });
  picker.addEventListener('input', () => { onChange(picker.value); applyToken(picker.value); });
  applyToken(value);
  row.appendChild(btnLabel);
  row.appendChild(btnValue);
  row.appendChild(picker);
  wrapper.appendChild(row);
  return wrapper;
}

function renderPropertiesPanel() {
  propertiesEl.innerHTML = '';
  const element = getTemplateElement(selectedId);
  const isArt = selectedId === 'artwork';
  const show = Boolean(selectedId && (isArt || element));
  if (propertiesPanelEl) {
    propertiesPanelEl.hidden = !show;
  }
  if (!show) {
    return;
  }
  if (isArt) {
    const title = document.createElement('h3');
    title.className = 'editor-properties__title';
    title.textContent = 'album art';
    propertiesEl.appendChild(title);
    const hint = document.createElement('p');
    hint.className = 'editor-panel__hint';
    hint.textContent = 'album art controls live in the background panel below - size, position and frame. drag it on the canvas or use the size/x/y fields.';
    propertiesEl.appendChild(hint);
    return;
  }
  const title = document.createElement('h3');
  title.className = 'editor-properties__title';
  title.textContent = `${element.kind} element`;
  propertiesEl.appendChild(title);

  if (element.kind === 'text') {
    propertiesEl.appendChild(fieldText(element.text, 'text', (value) => { element.text = value; markDirty(); }));
  } else {
    const slotOptions = (element.kind === 'list')
      ? [{ value: 'artists', label: 'top artists' }, { value: 'tracks', label: 'top tracks' }]
      : [{ value: 'minutes', label: 'minutes listened' }, { value: 'genre', label: 'top genre' }];
    propertiesEl.appendChild(fieldSelect(slotOptions, element.slot, 'show', (value) => { element.slot = value; render(); renderElementsList(); }));
    propertiesEl.appendChild(fieldNumber(element.maxWidth || 0, 'max width', (value) => { element.maxWidth = value; markDirty(); }));
    propertiesEl.appendChild(fieldNumber(element.minFontSize || 24, 'min font size', (value) => { element.minFontSize = value; markDirty(); }));
  }
  if (element.kind !== 'text') {
    propertiesEl.appendChild(fieldToggle(element.prefix !== false, 'number prefix', (value) => { element.prefix = value; markDirty(); }));
  }
  const fontOptions = FONT_FAMILIES.slice();
  const currentFont = element.font.family || 'Nunito';
  if (!fontOptions.some((option) => option.value === currentFont)) {
    fontOptions.push({ value: currentFont, label: currentFont });
  }
  propertiesEl.appendChild(fieldSelect(fontOptions, currentFont, 'font', (value) => { element.font.family = value; loadFonts([value]).then(() => render()); }));
  propertiesEl.appendChild(fieldSelect(FONT_WEIGHTS, element.font.weight || 700, 'weight', (value) => { element.font.weight = Number(value); markDirty(); }));
  propertiesEl.appendChild(fieldNumber(element.font.size || 48, 'font size', (value) => { element.font.size = value; markDirty(); }));
  propertiesEl.appendChild(fieldColor(element.color, (value) => { element.color = value; markDirty(); }));
  propertiesEl.appendChild(fieldNumber(element.x, 'x', (value) => { element.x = value; markDirty(); }));
  propertiesEl.appendChild(fieldNumber(element.y, 'y', (value) => { element.y = value; markDirty(); }));
}

function markDirty() {
  renderElementsList();
  render();
}

function renderSamples() {
  samplesEl.innerHTML = '';
  SAMPLES.forEach((sample) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'editor-sample';
    btn.classList.toggle('is-active', sample.id === sampleId);
    btn.title = sample.description;
    const name = document.createElement('span');
    name.className = 'editor-sample__name';
    name.textContent = sample.label;
    const desc = document.createElement('span');
    desc.className = 'editor-sample__desc';
    desc.textContent = sample.description;
    btn.appendChild(name);
    btn.appendChild(desc);
    btn.addEventListener('click', () => {
      sampleId = sample.id;
      data = getSampleData(sampleId).data;
      renderSamples();
      render();
    });
    samplesEl.appendChild(btn);
  });
}

function renderBackgroundControls() {
  const background = template.background;
  bgTypeEl.querySelectorAll('[data-bg-type]').forEach((btn) => {
    btn.classList.toggle('is-active', btn.dataset.bgType === background.type);
  });
  bgSolidField.hidden = background.type !== 'solid';
  bgGradientField.hidden = background.type !== 'gradient';
  bgImageField.hidden = background.type !== 'image';
  bgAngleField.hidden = background.type !== 'gradient';
  if (bgImageHint) {
    bgImageHint.hidden = background.type !== 'image';
  }
  if (background.type === 'solid') {
    bgColorInput.value = background.color || '#000000';
    if (bgColorHex) {
      bgColorHex.textContent = background.color || '#000000';
    }
  }
  if (background.type === 'gradient') {
    bgAngleInput.value = String(background.angle || 135);
    bgAngleValue.textContent = String(background.angle || 135);
    renderGradientSwatches();
  }
}

function renderGradientSwatches() {
  bgColorsEl.innerHTML = '';
  const colors = template.background.colors || [];
  colors.forEach((color, index) => {
    const swatch = document.createElement('input');
    swatch.type = 'color';
    swatch.value = color;
    swatch.addEventListener('input', () => {
      template.background.colors[index] = swatch.value;
      render();
    });
    bgColorsEl.appendChild(swatch);
  });
  const add = document.createElement('button');
  add.type = 'button';
  add.className = 'editor-swatch-add';
  add.textContent = '+';
  add.addEventListener('click', () => {
    (template.background.colors = template.background.colors || []).push('#888888');
    renderGradientSwatches();
    render();
  });
  bgColorsEl.appendChild(add);
}

function renderTopControls() {
  nameInput.value = template.name;
  slugInput.value = template.slug;
  categorySelect.value = template.meta.category || 'abstract';
  tagsInput.value = Array.isArray(template.meta.tags) ? template.meta.tags.join(', ') : '';
  paletteLabelInput.value = template.palette.label;
  paletteValueInput.value = template.palette.value;
  artEnabledInput.checked = template.artwork.enabled !== false;
  artFrameInput.checked = template.artwork.frame !== false;
  artXInput.value = String(template.artwork.x);
  artYInput.value = String(template.artwork.y);
  artSizeInput.value = String(template.artwork.size);
  renderBackgroundControls();
}

function showToast(message, tone = 'info') {
  toastEl.hidden = false;
  toastEl.textContent = message;
  toastEl.dataset.tone = tone;
  window.setTimeout(() => {
    toastEl.hidden = true;
  }, 4200);
}

function handlePointerDown(event) {
  const point = canvasPoint(event);
  const bounds = boundsForSelection(selectedId);
  const handleSize = 22;
  if (bounds && point.x >= bounds.x + bounds.width - handleSize && point.x <= bounds.x + bounds.width + handleSize
    && point.y >= bounds.y + bounds.height - handleSize && point.y <= bounds.y + bounds.height + handleSize) {
    const target = selectedId;
    const element = getTemplateElement(target);
    editing = {
      mode: 'resize',
      target,
      start: point,
      originalSize: target === 'artwork' ? template.artwork.size : element.font.size,
      originalLineHeight: element ? element.lineHeight : 0,
    };
    event.preventDefault();
    return;
  }
  const hit = hitTest(point);
  if (hit) {
    selectElement(hit);
    const element = getTemplateElement(hit);
    editing = {
      mode: 'move',
      target: hit,
      start: point,
      originalX: hit === 'artwork' ? template.artwork.x : element.x,
      originalY: hit === 'artwork' ? template.artwork.y : element.y,
    };
  } else {
    selectedId = null;
    renderElementsList();
    renderPropertiesPanel();
    render();
  }
}

function handlePointerMove(event) {
  if (!editing) {
    return;
  }
  const point = canvasPoint(event);
  if (editing.mode === 'move') {
    const dx = Math.round(point.x - editing.start.x);
    const dy = Math.round(point.y - editing.start.y);
    const current = editing.target === 'artwork' ? artworkBounds() : measureBounds(getTemplateElement(editing.target));
    const proposed = {
      x: editing.originalX + dx,
      y: editing.originalY + dy,
      width: current.width,
      height: current.height,
    };
    const snapped = snapBounds(proposed, editing.target);
    positionTarget(editing.target, snapped.bounds.x, snapped.bounds.y);
    guides = snapped.guides;
    render();
    return;
  }
  if (editing.mode === 'resize') {
    const delta = Math.round(point.y - editing.start.y);
    if (editing.target === 'artwork') {
      template.artwork.size = Math.max(80, editing.originalSize + delta);
    } else {
      const element = getTemplateElement(editing.target);
      const next = Math.max(8, editing.originalSize + delta);
      element.font.size = next;
      if (element.kind === 'list' && editing.originalLineHeight) {
        element.lineHeight = Math.max(8, Math.round((editing.originalLineHeight * next) / editing.originalSize));
      }
    }
    render();
  }
}

function handlePointerUp() {
  if (editing) {
    editing = null;
    guides = [];
    renderPropertiesPanel();
    render();
  }
}

function buildExportPayload() {
  const payload = {
    name: nameInput.value.trim() || 'Untitled',
    slug: slugInput.value.trim().toLowerCase() || 'my-template',
    meta: {
      category: categorySelect.value,
      tags: tagsInput.value.split(',').map((tag) => tag.trim()).filter(Boolean),
    },
    canvas: { width: 1080, height: 1920 },
    palette: deepClone(template.palette),
    background: deepClone(template.background),
    artwork: deepClone(template.artwork),
    elements: deepClone(template.elements),
  };
  return payload;
}

function exportTemplate() {
  const payload = buildExportPayload();
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${payload.slug}.json`;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  showToast('template exported as a json file.', 'success');
}

async function importTemplate(file) {
  if (!file) {
    return;
  }
  try {
    const text = await file.text();
    const parsed = JSON.parse(text);
    if (!parsed || typeof parsed !== 'object' || !Array.isArray(parsed.elements)) {
      throw new Error('not a valid template file.');
    }
    const imported = normaliseTemplate(parsed);
    template = deepClone(imported);
    if (!template.slug) {
      template.slug = 'imported-template';
    }
    slugTouched = true;
    renderTopControls();
    renderSamples();
    renderElementsList();
    renderPropertiesPanel();
    await loadFonts(templateFontFamilies(template));
    render();
    showToast('template imported. tweak it and submit.', 'success');
  } catch (error) {
    console.error('Import failed', error);
    showToast(error.message || 'could not import that file.', 'error');
  }
}

async function buildTemplatePayload() {
  const templatePayload = deepClone(template);
  templatePayload.name = nameInput.value.trim();
  templatePayload.slug = slugInput.value.trim().toLowerCase();
  templatePayload.meta = {
    category: categorySelect.value,
    tags: tagsInput.value.split(',').map((tag) => tag.trim()).filter(Boolean),
    featured: false,
  };
  templatePayload.palette = {
    label: paletteLabelInput.value,
    value: paletteValueInput.value,
  };
  templatePayload.background = deepClone(template.background);
  templatePayload.artwork = deepClone(template.artwork);
  templatePayload.elements = deepClone(template.elements);
  templatePayload.canvas = template.canvas;
  if (templatePayload.background.type === 'image' && bgIsLocal && bgUploadFile) {
    const formData = new FormData();
    formData.append('slug', templatePayload.slug);
    formData.append('asset', bgUploadFile, bgUploadFile.name || 'background.png');
    const headers = await turnstileHeaders();
    const response = await fetch('/api/templates/asset', {
      method: 'POST',
      body: formData,
      headers,
    });
    if (!response.ok) {
      throw new Error(await parseError(response));
    }
    const payload = await response.json();
    templatePayload.background.src = payload.url;
  }
  templatePayload.canvas = { width: 1080, height: 1920 };
  delete templatePayload._backgroundImage;
  return templatePayload;
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

async function refreshTurnstileToken() {
  if (!turnstileEnabled) {
    return null;
  }
  if (turnstileWaiter) {
    return turnstileWaiter;
  }
  if (!window.turnstile || typeof window.turnstile.execute !== 'function' || turnstileWidgetId === null) {
    return null;
  }
  if (turnstileWrapper) {
    turnstileWrapper.hidden = false;
  }
  turnstileToken = null;
  turnstileWaiter = new Promise((resolve) => {
    turnstileWaiterResolve = resolve;
  });
  try {
    window.turnstile.execute(turnstileWidgetId);
  } catch (error) {
    console.warn('Turnstile execute failed', error);
    turnstileWaiter = null;
    turnstileWaiterResolve = null;
    return null;
  }
  return turnstileWaiter;
}

async function awaitTurnstileToken() {
  if (!turnstileEnabled) {
    return null;
  }
  if (turnstileToken) {
    return turnstileToken;
  }
  const waiter = await refreshTurnstileToken();
  if (!waiter) {
    return null;
  }
  return waiter;
}

async function turnstileHeaders() {
  if (!turnstileEnabled) {
    return {};
  }
  const token = await refreshTurnstileToken();
  if (!token) {
    throw new Error('complete the human verification to continue.');
  }
  return { 'X-Turnstile-Token': token };
}

async function ensureTurnstile() {
  if (!turnstileEnabled) {
    return true;
  }
  try {
    const token = await awaitTurnstileToken();
    if (token) {
      return true;
    }
    showToast('complete the human check to submit.', 'info');
    return false;
  } catch (error) {
    showToast(error.message || 'complete the human check to submit.', 'info');
    return false;
  }
}

async function submitTemplate() {
  const name = nameInput.value.trim();
  const slug = slugInput.value.trim().toLowerCase();
  if (!name) {
    showToast('give your template a name.', 'error');
    return;
  }
  if (!/^[a-z0-9][a-z0-9-]{0,48}$/.test(slug) || slug.length > 48) {
    showToast('slug can only use lowercase letters, numbers and dashes.', 'error');
    return;
  }
  const verified = await ensureTurnstile();
  if (!verified) {
    return;
  }
  setCreatorDisplayFields();
  submitBtn.disabled = true;
  submitBtn.textContent = 'submitting...';
  try {
    const templatePayload = await buildTemplatePayload();
    const creator = await buildCreatorPayload();
    const headers = await turnstileHeaders();
    const response = await fetch('/api/templates/submit', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...headers,
      },
      body: JSON.stringify({ creator, template: templatePayload, reason: '' }),
    });
    if (!response.ok) {
      throw new Error(await parseError(response));
    }
    const payload = await response.json();
    showToast(`submitted for review (${payload.status}). a maintainer will review it soon.`, 'success');
    if (turnstileEnabled) {
      turnstileToken = null;
    }
    window.setTimeout(() => {
      window.location.href = '/';
    }, 900);
  } catch (error) {
    console.error(error);
    showToast(error.message || 'something went wrong submitting.', 'error');
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = 'submit for review';
  }
}

function setCreatorDisplayFields() {
  setCreatorDisplay({ name: creatorNameInput.value, website: creatorWebsiteInput.value, bio: creatorBioInput.value });
}

async function loadCreatorInfo() {
  const display = getCreatorDisplay();
  creatorNameInput.value = display.name || '';
  creatorWebsiteInput.value = display.website || '';
  creatorBioInput.value = display.bio || '';
  const id = await getCreatorId();
  creatorIdEl.textContent = `verified identity: @${id.slice(0, 10)} (stays the same across your templates)`;
}

async function waitForTurnstileApi(maxWait = 10000) {
  if (window.turnstile && typeof window.turnstile.render === 'function') {
    return true;
  }
  return new Promise((resolve) => {
    const start = Date.now();
    const poll = window.setInterval(() => {
      if (window.turnstile && typeof window.turnstile.render === 'function') {
        window.clearInterval(poll);
        resolve(true);
        return;
      }
      if (Date.now() - start >= maxWait) {
        window.clearInterval(poll);
        resolve(false);
      }
    }, 150);
  });
}

async function initTurnstile() {
  try {
    const response = await fetch('/api/client-config', { cache: 'no-store' });
    const payload = await response.json();
    turnstileEnabled = Boolean(payload.turnstileEnabled && payload.turnstileSiteKey);
    turnstileSiteKey = payload.turnstileSiteKey || '';
  } catch (error) {
    turnstileEnabled = false;
  }
  if (turnstileEnabled) {
    const ready = await waitForTurnstileApi();
    if (ready && window.turnstile && typeof window.turnstile.render === 'function') {
      turnstileWrapper = document.createElement('div');
      turnstileWrapper.className = 'editor-turnstile';
      turnstileWrapper.hidden = true;
      const label = document.createElement('span');
      label.textContent = 'verification';
      turnstileWrapper.appendChild(label);
      const container = document.createElement('div');
      turnstileWrapper.appendChild(container);
      document.querySelector('.editor-header__actions').appendChild(turnstileWrapper);
      turnstileWidgetId = window.turnstile.render(container, {
        sitekey: turnstileSiteKey,
        action: 'submit_template',
        callback: (token) => {
          turnstileToken = token;
          if (turnstileWrapper) {
            turnstileWrapper.hidden = true;
          }
          if (turnstileWaiterResolve) {
            turnstileWaiterResolve(token);
          }
          turnstileWaiter = null;
          turnstileWaiterResolve = null;
          showToast('verified! ready to submit.', 'success');
        },
        'expired-callback': () => {
          turnstileToken = null;
          if (turnstileWaiterResolve) {
            turnstileWaiterResolve(null);
          }
          turnstileWaiter = null;
          turnstileWaiterResolve = null;
        },
        'error-callback': () => {
          turnstileToken = null;
          if (turnstileWaiterResolve) {
            turnstileWaiterResolve(null);
          }
          turnstileWaiter = null;
          turnstileWaiterResolve = null;
        },
      });
    }
  }
}

async function init() {
  const params = new URLSearchParams(window.location.search);
  const slug = params.get('template') || 'black';
  try {
    const base = await fetchTemplate(slug);
    template = normaliseTemplate(deepClone(base));
    if (base.origin === 'official' || base.creator.id === 'official') {
      template.name = 'My Template';
      template.slug = 'my-template';
    }
  } catch (error) {
    template = normaliseTemplate({ name: 'My Template', slug: 'my-template', elements: [] });
  }
  CATEGORIES.forEach((category) => {
    const option = document.createElement('option');
    option.value = category;
    option.textContent = category;
    categorySelect.appendChild(option);
  });

  bindEvents();
  renderTopControls();
  renderSamples();
  renderElementsList();
  renderPropertiesPanel();
  loadCreatorInfo();
  initTurnstile();
  await loadFonts(templateFontFamilies(template));
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(() => render());
  }
  sampleArtPromise.then((image) => {
    sampleArt = image;
    render();
  });
  render();
}

function bindEvents() {
  nameInput.addEventListener('input', () => {
    template.name = nameInput.value;
    if (!slugTouched) {
      const candidate = nameInput.value.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
      slugInput.value = candidate || 'my-template';
      template.slug = slugInput.value;
    }
  });
  slugInput.addEventListener('input', () => {
    slugTouched = true;
    template.slug = slugInput.value.trim().toLowerCase();
  });
  categorySelect.addEventListener('change', () => { template.meta.category = categorySelect.value; });
  tagsInput.addEventListener('input', () => {
    template.meta.tags = tagsInput.value.split(',').map((tag) => tag.trim()).filter(Boolean);
  });
  bgTypeEl.querySelectorAll('[data-bg-type]').forEach((btn) => {
    btn.addEventListener('click', () => {
      template.background = template.background || { type: 'solid', color: '#000000' };
      template.background.type = btn.dataset.bgType;
      if (btn.dataset.bgType === 'solid' && !template.background.color) {
        template.background.color = '#000000';
      }
      if (btn.dataset.bgType === 'gradient' && !template.background.colors) {
        template.background.colors = ['#1e1b2e', '#c084fc'];
        template.background.angle = 135;
      }
      renderBackgroundControls();
      render();
    });
  });
  bgColorInput.addEventListener('input', () => {
    template.background.color = bgColorInput.value;
    if (bgColorHex) {
      bgColorHex.textContent = bgColorInput.value;
    }
    render();
  });
  if (bgImageUploadBtn && bgImageFile) {
    bgImageUploadBtn.addEventListener('click', () => bgImageFile.click());
  }
  bgAngleInput.addEventListener('input', () => {
    template.background.angle = Number(bgAngleInput.value);
    bgAngleValue.textContent = bgAngleInput.value;
    render();
  });
  bgImageFile.addEventListener('change', async (event) => {
    const file = event.target.files && event.target.files[0];
    if (!file) {
      return;
    }
    try {
      const dataUrl = await readFileAsDataUrl(file);
      template.background = { type: 'image', src: dataUrl };
      bgIsLocal = true;
      bgUploadFile = file;
      bgImageHint.textContent = 'image will be uploaded with your submission.';
      renderBackgroundControls();
      render();
    } catch (error) {
      showToast('could not load that image.', 'error');
    }
  });
  paletteLabelInput.addEventListener('input', () => { template.palette.label = paletteLabelInput.value; renderPropertiesPanel(); render(); });
  paletteValueInput.addEventListener('input', () => { template.palette.value = paletteValueInput.value; renderPropertiesPanel(); render(); });
  artEnabledInput.addEventListener('change', () => { template.artwork.enabled = artEnabledInput.checked; render(); });
  artFrameInput.addEventListener('change', () => { template.artwork.frame = artFrameInput.checked; render(); });
  artXInput.addEventListener('input', () => { template.artwork.x = Number(artXInput.value) || 0; render(); });
  artYInput.addEventListener('input', () => { template.artwork.y = Number(artYInput.value) || 0; render(); });
  artSizeInput.addEventListener('input', () => { template.artwork.size = Number(artSizeInput.value) || 0; render(); });
  resetBtn.addEventListener('click', () => {
    showToast('reset the canvas to the starting template.');
    window.location.reload();
  });
  submitBtn.addEventListener('click', submitTemplate);
  if (exportBtn) {
    exportBtn.addEventListener('click', exportTemplate);
  }
  if (importBtn && importFileInput) {
    importBtn.addEventListener('click', () => importFileInput.click());
    importFileInput.addEventListener('change', (event) => {
      const file = event.target.files && event.target.files[0];
      importTemplate(file);
      event.target.value = '';
    });
  }
  document.querySelectorAll('[data-add]').forEach((btn) => {
    btn.addEventListener('click', () => addElement(btn.dataset.add));
  });
  canvas.addEventListener('pointerdown', handlePointerDown);
  window.addEventListener('pointermove', handlePointerMove);
  window.addEventListener('pointerup', handlePointerUp);
}

window.addEventListener('load', init);
