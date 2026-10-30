import { normaliseGenreLabel } from '../utils.js';

export const DEFAULT_CANVAS = { width: 1080, height: 1920 };

export function normaliseTemplate(raw) {
  const template = raw && typeof raw === 'object' ? raw : {};
  const canvas = template.canvas || {};
  const palette = template.palette || {};
  const background = template.background || { type: 'solid', color: '#000000' };
  const artwork = template.artwork || {};
  const elements = Array.isArray(template.elements) ? template.elements : [];
  return {
    version: template.version || 1,
    slug: template.slug || 'untitled',
    name: template.name || 'Untitled',
    creator: template.creator || { id: 'unknown', name: 'Unknown' },
    meta: template.meta || {},
    canvas: {
      width: Number.isFinite(canvas.width) ? canvas.width : DEFAULT_CANVAS.width,
      height: Number.isFinite(canvas.height) ? canvas.height : DEFAULT_CANVAS.height,
    },
    palette: {
      label: palette.label || '#ffffff',
      value: palette.value || '#ffffff',
    },
    background: normaliseBackground(background),
    artwork: {
      enabled: artwork.enabled !== false,
      contain: artwork.contain === true,
      x: Number.isFinite(artwork.x) ? artwork.x : 268,
      y: Number.isFinite(artwork.y) ? artwork.y : 244,
      size: Number.isFinite(artwork.size) ? artwork.size : 544,
      borderRadius: Number.isFinite(artwork.borderRadius) ? artwork.borderRadius : 32,
      frame: artwork.frame !== false,
      frameWidth: Number.isFinite(artwork.frameWidth) ? artwork.frameWidth : 10,
    },
    elements,
  };
}

function normaliseBackground(background) {
  if (background.type === 'image') {
    return { type: 'image', src: background.src || '' };
  }
  if (background.type === 'solid') {
    return { type: 'solid', color: background.color || '#000000' };
  }
  const colors = Array.isArray(background.colors) ? background.colors : ['#000000', '#333333'];
  return {
    type: 'gradient',
    colors: colors.length ? colors : ['#000000', '#333333'],
    angle: Number.isFinite(background.angle) ? background.angle : 135,
  };
}

export function resolveColor(template, color) {
  const palette = template.palette || {};
  if (color === 'label') {
    return palette.label;
  }
  if (color === 'value') {
    return palette.value;
  }
  if (typeof color === 'string' && /^#[0-9a-f]{6}$/i.test(color)) {
    return color;
  }
  return palette.value;
}

export function resolveSlotDisplay(data, slot) {
  const safeData = data && typeof data === 'object' ? data : {};
  switch (slot) {
    case 'artists':
      return Array.isArray(safeData.artists) ? safeData.artists : [];
    case 'tracks':
      return Array.isArray(safeData.tracks) ? safeData.tracks : [];
    case 'minutes':
      if (typeof safeData.minutes === 'string') {
        return safeData.minutes;
      }
      if (typeof safeData.minutes === 'number') {
        return String(safeData.minutes);
      }
      return '0';
    case 'genre':
      return normaliseGenreLabel(safeData.genre);
    default:
      return '';
  }
}

export function fontString(font, sizeOverride) {
  const family = (font && font.family) || 'Nunito';
  const weight = Number.isFinite(font && font.weight) ? font.weight : 700;
  const size = sizeOverride || (font && Number.isFinite(font.size) ? font.size : 48);
  return `${weight} ${size}px ${family}`;
}

function ellipsize(ctx, text, maxWidth) {
  const value = typeof text === 'string' ? text : '';
  if (!maxWidth || maxWidth <= 0) {
    return value;
  }
  if (ctx.measureText(value).width <= maxWidth) {
    return value;
  }
  const ellipsis = '…';
  let end = value.length;
  while (end > 0) {
    const candidate = `${value.slice(0, end).trimEnd()}${ellipsis}`;
    if (!candidate || ctx.measureText(candidate).width <= maxWidth) {
      return candidate || ellipsis;
    }
    end -= 1;
  }
  return ellipsis;
}

export function fitText(ctx, text, { font = { weight: 700, size: 48, family: 'Nunito' }, maxWidth, minFontSize = 12, ellipsizeText = true } = {}) {
  let size = Number.isFinite(font && font.size) ? font.size : 48;
  const value = typeof text === 'string' ? text : '';
  let current = `${(font && font.weight) || 700} ${size}px ${(font && font.family) || 'Nunito'}`;
  ctx.save();
  ctx.font = current;
  if (maxWidth && maxWidth > 0) {
    const floor = Number.isFinite(minFontSize) ? minFontSize : 12;
    while (size > floor && ctx.measureText(value).width > maxWidth) {
      size -= 2;
      current = `${(font && font.weight) || 700} ${size}px ${(font && font.family) || 'Nunito'}`;
      ctx.font = current;
    }
    if (ctx.measureText(value).width > maxWidth && ellipsizeText) {
      const truncated = ellipsize(ctx, value, maxWidth);
      ctx.restore();
      return { text: truncated, font: current };
    }
  }
  ctx.restore();
  return { text: value, font: current };
}

function drawBackground(ctx, template) {
  const { width, height } = template.canvas;
  const background = template.background;
  if (background.type === 'image') {
    const image = background._image;
    if (image && image.complete && image.naturalWidth > 0) {
      ctx.drawImage(image, 0, 0, width, height);
    } else {
      ctx.fillStyle = '#000000';
      ctx.fillRect(0, 0, width, height);
    }
    return;
  }
  if (background.type === 'solid') {
    ctx.fillStyle = background.color || '#000000';
    ctx.fillRect(0, 0, width, height);
    return;
  }
  const colors = background.colors && background.colors.length ? background.colors : ['#000000', '#333333'];
  const angle = Number.isFinite(background.angle) ? background.angle : 135;
  const rad = (angle * Math.PI) / 180;
  const x = Math.cos(rad);
  const y = Math.sin(rad);
  const cx = width / 2;
  const cy = height / 2;
  const len = Math.abs(width * x) + Math.abs(height * y);
  const gradient = ctx.createLinearGradient(cx - x * (len / 2), cy - y * (len / 2), cx + x * (len / 2), cy + y * (len / 2));
  colors.forEach((color, index) => {
    const stop = colors.length === 1 ? 0 : index / (colors.length - 1);
    gradient.addColorStop(stop, color);
  });
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, width, height);
}

const CENTER_FOCUS = { x: 0.5, y: 0.5 };
const FOCUS_SAMPLE_SIZE = 96;
const focusCache = new WeakMap();

function createScratchCanvas(ctx, width, height) {
  if (typeof OffscreenCanvas !== 'undefined') {
    return new OffscreenCanvas(width, height);
  }
  if (typeof document !== 'undefined') {
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    return canvas;
  }
  try {
    return new ctx.canvas.constructor(width, height);
  } catch {
    return null;
  }
}

// skin tones count most (faces), edges a little, so tall photos keep the head in frame
function pixelInterest(pixels, width, x, y) {
  const index = (y * width + x) * 4;
  const r = pixels[index];
  const g = pixels[index + 1];
  const b = pixels[index + 2];
  const luma = (r, g, b) => 0.2126 * r + 0.7152 * g + 0.0722 * b;
  const lum = luma(r, g, b);
  let skin = 0;
  const mag = Math.sqrt(r * r + g * g + b * b) || 1;
  const distance = Math.hypot(r / mag - 0.78, g / mag - 0.57, b / mag - 0.44);
  if (1 - distance > 0.8 && lum > 0.2 * 255) {
    skin = (1 - distance - 0.8) / 0.2;
  }
  const at = (dx, dy) => {
    const i = ((y + dy) * width + (x + dx)) * 4;
    return luma(pixels[i], pixels[i + 1], pixels[i + 2]);
  };
  const edge = Math.abs(4 * lum - at(-1, 0) - at(1, 0) - at(0, -1) - at(0, 1)) / 255;
  return skin * 1.8 + Math.min(edge, 1) * 0.2;
}

function computeCropFocus(ctx, art, imgWidth, imgHeight) {
  const ratio = FOCUS_SAMPLE_SIZE / Math.max(imgWidth, imgHeight);
  const width = Math.max(3, Math.round(imgWidth * ratio));
  const height = Math.max(3, Math.round(imgHeight * ratio));
  const scratch = createScratchCanvas(ctx, width, height);
  if (!scratch) {
    return CENTER_FOCUS;
  }
  const sctx = scratch.getContext('2d');
  sctx.drawImage(art, 0, 0, width, height);
  const pixels = sctx.getImageData(0, 0, width, height).data;

  const rows = new Array(height).fill(0);
  let total = 0;
  for (let y = 1; y < height - 1; y += 1) {
    for (let x = 1; x < width - 1; x += 1) {
      const score = pixelInterest(pixels, width, x, y);
      rows[y] += score;
      total += score;
    }
  }
  const travel = height - width;
  if (travel <= 0) {
    return CENTER_FOCUS;
  }
  if (total < 1) {
    return { x: 0.5, y: 0.35 };
  }
  for (let y = 0; y < height; y += 1) {
    rows[y] *= 1.4 - (0.9 * y) / height;
  }
  let best = travel / 2;
  let bestScore = -Infinity;
  for (let start = 0; start <= travel; start += 1) {
    let score = 0;
    for (let i = 0; i < width; i += 1) {
      score += rows[start + i] * (0.6 + 0.4 * Math.sin((Math.PI * (i + 0.5)) / width));
    }
    if (score > bestScore) {
      bestScore = score;
      best = start;
    }
  }
  return { x: 0.5, y: best / travel };
}

function findCropFocus(ctx, art) {
  const imgWidth = art.naturalWidth || art.width;
  const imgHeight = art.naturalHeight || art.height;
  if (!imgWidth || !imgHeight || (imgHeight - imgWidth) / imgHeight < 0.02) {
    return CENTER_FOCUS;
  }
  const key = `${typeof art.currentSrc === 'string' ? art.currentSrc : ''}|${typeof art.src === 'string' ? art.src : ''}|${imgWidth}x${imgHeight}`;
  const cached = focusCache.get(art);
  if (cached && cached.key === key) {
    return cached.focus;
  }
  let focus = CENTER_FOCUS;
  try {
    focus = computeCropFocus(ctx, art, imgWidth, imgHeight);
  } catch {
    focus = CENTER_FOCUS;
  }
  focusCache.set(art, { key, focus });
  return focus;
}

function drawArtwork(ctx, template, art, artTransform) {
  const config = template.artwork;
  if (!config || config.enabled === false) {
    return;
  }
  if (!art || !art.complete || !art.naturalWidth || art.naturalWidth <= 0) {
    return;
  }
  const destX = config.x;
  const destY = config.y;
  const destSize = config.size;
  const imgWidth = art.naturalWidth;
  const imgHeight = art.naturalHeight;
  const fitScale = config.contain ? Math.min(destSize / imgWidth, destSize / imgHeight) : Math.max(destSize / imgWidth, destSize / imgHeight);
  const transform = artTransform || {};
  const scale = transform.allowTransform && Number.isFinite(transform.scale) ? transform.scale : 1;
  const offsetX = transform.allowTransform && Number.isFinite(transform.offsetX) ? transform.offsetX : 0;
  const offsetY = transform.allowTransform && Number.isFinite(transform.offsetY) ? transform.offsetY : 0;

  const drawWidth = imgWidth * fitScale * scale;
  const drawHeight = imgHeight * fitScale * scale;
  const focus = config.contain ? { x: 0.5, y: 0.5 } : findCropFocus(ctx, art);
  const drawX = destX + (destSize - drawWidth) * focus.x + offsetX;
  const drawY = destY + (destSize - drawHeight) * focus.y + offsetY;
  const radius = Number.isFinite(config.borderRadius) ? config.borderRadius : 32;

  ctx.save();
  ctx.beginPath();
  if (typeof ctx.roundRect === 'function') {
    ctx.roundRect(destX, destY, destSize, destSize, radius);
  } else {
    ctx.rect(destX, destY, destSize, destSize);
  }
  ctx.clip();
  ctx.drawImage(art, 0, 0, imgWidth, imgHeight, drawX, drawY, drawWidth, drawHeight);
  ctx.restore();

  if (config.frame) {
    ctx.save();
    const gradient = ctx.createLinearGradient(destX, destY, destX, destY + destSize);
    gradient.addColorStop(0, 'rgba(5, 8, 16, 0.55)');
    gradient.addColorStop(1, 'rgba(5, 8, 16, 0.25)');
    const strokeWidth = Number.isFinite(config.frameWidth) ? config.frameWidth : 10;
    if (typeof ctx.roundRect === 'function') {
      ctx.beginPath();
      ctx.roundRect(destX, destY, destSize, destSize, radius);
      ctx.strokeStyle = gradient;
      ctx.lineWidth = strokeWidth;
      ctx.stroke();
    } else {
      ctx.strokeStyle = gradient;
      ctx.lineWidth = strokeWidth;
      ctx.strokeRect(destX + strokeWidth / 2, destY + strokeWidth / 2, destSize - strokeWidth, destSize - strokeWidth);
    }
    ctx.restore();
  }
}

function drawElements(ctx, template, data) {
  const elements = Array.isArray(template.elements) ? template.elements : [];
  for (const element of elements) {
    drawElement(ctx, template, element, data);
  }
}

function drawElement(ctx, template, element, data) {
  const font = element.font || { weight: 700, size: 48, family: 'Nunito' };
  const color = resolveColor(template, element.color);
  const x = Number.isFinite(element.x) ? element.x : 0;
  const y = Number.isFinite(element.y) ? element.y : 0;
  const baseline = element.baseline === 'alphabetic' ? 'alphabetic' : 'top';
  const align = ['left', 'center', 'right'].includes(element.align) ? element.align : 'left';
  const maxWidth = Number.isFinite(element.maxWidth) ? element.maxWidth : 0;

  ctx.save();
  ctx.font = fontString(font);
  ctx.fillStyle = color;
  ctx.textBaseline = baseline;
  ctx.textAlign = align;

  if (element.kind === 'text') {
    ctx.fillText(typeof element.text === 'string' ? element.text : '', x, y);
  } else if (element.kind === 'list') {
    const items = resolveSlotDisplay(data, element.slot);
    const lineHeight = Number.isFinite(element.lineHeight) ? element.lineHeight : 72;
    const prefix = element.prefix !== false;
    const list = Array.isArray(items) ? items : [];
    list.forEach((item, index) => {
      const value = typeof item === 'string' ? item : '';
      let label = value;
      if (prefix) {
        const prefixText = `${index + 1}. `;
        const prefixWidth = ctx.measureText(prefixText).width;
        const availableWidth = Math.max(0, maxWidth - prefixWidth);
        label = `${prefixText}${ellipsize(ctx, value, availableWidth)}`;
      } else {
        label = ellipsize(ctx, value, maxWidth);
      }
      ctx.fillText(label, x, y + index * lineHeight);
    });
  } else {
    const value = resolveSlotDisplay(data, element.slot);
    const minFontSize = Number.isFinite(element.minFontSize) ? element.minFontSize : 12;
    const layout = fitText(ctx, value, {
      font,
      maxWidth,
      minFontSize,
      ellipsizeText: element.ellipsize !== false,
    });
    ctx.font = layout.font;
    ctx.fillText(layout.text, x, y);
  }
  ctx.restore();
}

const WATERMARK_BRAND = 'wrapped';
const WATERMARK_DOMAIN = '.devmatei.com';

function elementBoxes(ctx, template, data, artImage) {
  const boxes = [];
  const art = template.artwork;
  if (art && art.enabled !== false && artImage && artImage.naturalWidth > 0) {
    boxes.push({ left: art.x, top: art.y, right: art.x + art.size, bottom: art.y + art.size });
  }
  const elements = Array.isArray(template.elements) ? template.elements : [];
  for (const element of elements) {
    const size = (element.font && Number.isFinite(element.font.size)) ? element.font.size : 48;
    const x = Number.isFinite(element.x) ? element.x : 0;
    const y = Number.isFinite(element.y) ? element.y : 0;
    let lines = 1;
    let text = '';
    if (element.kind === 'text') {
      text = typeof element.text === 'string' ? element.text : '';
    } else if (element.kind === 'list') {
      const items = resolveSlotDisplay(data, element.slot);
      lines = Math.max(1, Array.isArray(items) ? items.length : 0);
      text = Array.isArray(items) ? items.reduce((a, b) => (String(b).length > a.length ? String(b) : a), '') : '';
    } else {
      text = String(resolveSlotDisplay(data, element.slot) || '');
    }
    ctx.font = fontString(element.font);
    let width = ctx.measureText(text).width + (element.kind === 'list' ? size * 1.4 : 0);
    if (Number.isFinite(element.maxWidth) && element.maxWidth > 0) {
      width = Math.min(width, element.maxWidth);
    }
    const left = element.align === 'right' ? x - width : element.align === 'center' ? x - width / 2 : x;
    const alphabetic = element.baseline === 'alphabetic';
    const top = alphabetic ? y - size : y;
    const lineHeight = Number.isFinite(element.lineHeight) ? element.lineHeight : 72;
    const extra = element.kind === 'list' ? (lines - 1) * lineHeight : 0;
    const gridWidth = Number.isFinite(element.maxWidth) && element.maxWidth > 0 ? element.maxWidth : width;
    const gridLeft = element.align === 'right' ? x - gridWidth : element.align === 'center' ? x - gridWidth / 2 : x;
    boxes.push({ left, top, right: left + width, bottom: (alphabetic ? y + size * 0.3 : y + size * 1.3) + extra, gridLeft, gridRight: gridLeft + gridWidth });
  }
  const { width, height } = template.canvas;
  return boxes
    .map((box) => ({ ...box, left: Math.max(0, box.left), top: Math.max(0, box.top), right: Math.min(width, box.right), bottom: Math.min(height, box.bottom) }))
    .filter((box) => box.right > box.left && box.bottom > box.top);
}

function hexToRgb(hex) {
  const match = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(hex || '');
  if (!match) return null;
  const digits = match[1].length === 3 ? match[1].replace(/./g, '$&$&') : match[1];
  const value = parseInt(digits, 16);
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
}

function relativeLuminance([r, g, b]) {
  const channel = (v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function contrastRatio(a, b) {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

function averageColor(ctx, rect) {
  try {
    const x = Math.max(0, Math.floor(rect.left));
    const y = Math.max(0, Math.floor(rect.top));
    const w = Math.max(1, Math.ceil(rect.right - rect.left));
    const h = Math.max(1, Math.ceil(rect.bottom - rect.top));
    const pixels = ctx.getImageData(x, y, w, h).data;
    const sum = [0, 0, 0];
    for (let i = 0; i < pixels.length; i += 4) {
      sum[0] += pixels[i];
      sum[1] += pixels[i + 1];
      sum[2] += pixels[i + 2];
    }
    const count = Math.max(1, pixels.length / 4);
    return sum.map((v) => v / count);
  } catch {
    return null;
  }
}

function measureWatermark(ctx, size) {
  ctx.font = `700 ${size}px Nunito`;
  const brand = ctx.measureText(WATERMARK_BRAND).width;
  ctx.font = `400 ${size}px Nunito`;
  const domain = ctx.measureText(WATERMARK_DOMAIN).width;
  return { brand, domain, width: brand + domain };
}

function placeWatermark(ctx, template, boxes) {
  const { width, height } = template.canvas;
  const margin = Math.round(Math.min(width, height) * 0.024);
  const contentRight = boxes.reduce((edge, box) => Math.max(edge, Math.min(box.gridRight ?? box.right, width - margin)), 0);
  const contentLeft = boxes.reduce((edge, box) => Math.min(edge, Math.max(box.gridLeft ?? box.left, margin)), width);
  const right = contentRight > width / 2 ? contentRight : width - margin;
  const left = contentLeft < width / 2 ? contentLeft : margin;
  const hits = (rect) => boxes.some((box) => rect.left < box.right + 8 && rect.right > box.left - 8
    && rect.top < box.bottom + 8 && rect.bottom > box.top - 8);
  const baseSize = Math.max(14, Math.round(width * 0.022));
  for (let size = baseSize; size >= Math.max(12, baseSize - 6); size -= 2) {
    const metrics = measureWatermark(ctx, size);
    const bottomY = height - margin;
    const topY = margin + size * 0.75;
    const spots = [
      { x: right - metrics.width, y: bottomY },
      { x: (width - metrics.width) / 2, y: bottomY },
      { x: left, y: bottomY },
      { x: right - metrics.width, y: topY },
    ];
    for (const spot of spots) {
      const rect = { left: spot.x, right: spot.x + metrics.width, top: spot.y - size * 0.75, bottom: spot.y + size * 0.25 };
      if (!hits(rect)) {
        return { ...spot, size, metrics, rect };
      }
    }
  }
  const size = Math.max(12, baseSize - 6);
  const metrics = measureWatermark(ctx, size);
  const x = right - metrics.width;
  const y = height - margin;
  return { x, y, size, metrics, rect: { left: x, right: x + metrics.width, top: y - size * 0.75, bottom: y + size * 0.25 }, crowded: true };
}

function drawWatermark(ctx, template, data, art) {
  ctx.save();
  const spot = placeWatermark(ctx, template, elementBoxes(ctx, template, data, art));
  const background = averageColor(ctx, spot.rect);
  let ink = hexToRgb(template.palette && template.palette.label) || [255, 255, 255];
  let alpha = 0.68;
  if (background) {
    const visible = (a) => contrastRatio(ink.map((v, i) => v * a + background[i] * (1 - a)), background);
    if (visible(alpha) < 2.8) {
      alpha = 0.78;
    }
    if (visible(1) < 1.6) {
      const light = contrastRatio([255, 255, 255], background) >= contrastRatio([17, 17, 17], background);
      ink = light ? [255, 255, 255] : [17, 17, 17];
      alpha = 0.7;
    }
  }
  ctx.fillStyle = `rgba(${ink.map(Math.round).join(', ')}, ${spot.crowded ? 0.9 : alpha})`;
  if (spot.crowded) {
    ctx.shadowColor = 'rgba(0, 0, 0, 0.45)';
    ctx.shadowBlur = spot.size * 0.4;
  }
  ctx.textAlign = 'left';
  ctx.textBaseline = 'alphabetic';
  ctx.font = `700 ${spot.size}px Nunito`;
  ctx.fillText(WATERMARK_BRAND, spot.x, spot.y);
  ctx.font = `400 ${spot.size}px Nunito`;
  ctx.fillText(WATERMARK_DOMAIN, spot.x + spot.metrics.brand, spot.y);
  ctx.restore();
}

export function renderTemplate(ctx, template, { data = {}, art = null, artTransform = {}, showElements = true, watermark = true } = {}) {
  const canvas = template.canvas || DEFAULT_CANVAS;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  drawBackground(ctx, template);
  drawArtwork(ctx, template, art, artTransform);
  if (showElements) {
    drawElements(ctx, template, data);
  }
  if (watermark) {
    drawWatermark(ctx, template, showElements ? data : {}, art);
  }
}

export function prepareBackgroundImage(template, onReady, onError) {
  const background = template && template.background;
  if (!background || background.type !== 'image') {
    if (typeof onReady === 'function') {
      onReady();
    }
    return;
  }
  if (background._image && background._image.complete) {
    if (typeof onReady === 'function') {
      onReady();
    }
    return;
  }
  const image = background._image || new Image();
  image.onload = () => {
    background._image = image;
    if (typeof onReady === 'function') {
      onReady();
    }
  };
  image.onerror = () => {
    background._image = null;
    if (typeof onError === 'function') {
      onError();
    }
  };
  image.src = background.src || '';
  background._image = image;
}
