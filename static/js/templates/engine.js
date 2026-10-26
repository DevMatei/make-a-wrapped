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

function drawWatermark(ctx, template, luminance) {
  const { width, height } = template.canvas;
  const label = 'make a wrapped · wrapped.devmatei.com';
  const baseFontSize = 30;
  const minimumFontSize = 12;
  const paddingX = 14;
  const paddingY = 9;
  ctx.save();
  ctx.font = `600 ${baseFontSize}px Nunito`;
  const scale = Math.min(1, Math.max(minimumFontSize / baseFontSize, (width - 24) / (ctx.measureText(label).width + paddingX * 2)));
  const fontSize = baseFontSize * scale;
  ctx.font = `600 ${fontSize}px Nunito`;
  const textWidth = ctx.measureText(label).width;
  const boxWidth = textWidth + paddingX * 2;
  const boxHeight = fontSize + paddingY * 2;
  const x = Math.max(8, width - boxWidth - 24);
  const y = Math.max(4, height - boxHeight - 24);
  const textColor = luminance > 0.5 ? '#111111' : '#ffffff';
  const backgroundColor = luminance > 0.5 ? 'rgba(255, 255, 255, 0.72)' : 'rgba(0, 0, 0, 0.5)';
  ctx.globalAlpha = 0.94;
  ctx.fillStyle = backgroundColor;
  if (typeof ctx.roundRect === 'function') {
    ctx.beginPath();
    ctx.roundRect(x, y, boxWidth, boxHeight, boxHeight / 2);
    ctx.fill();
  } else {
    ctx.fillRect(x, y, boxWidth, boxHeight);
  }
  ctx.font = `600 ${fontSize}px Nunito`;
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  ctx.fillStyle = textColor;
  ctx.fillText(label, width - 24 - paddingX, y + boxHeight / 2);
  ctx.restore();
}

function sampleLuminance(ctx, template) {
  const { width, height } = template.canvas;
  const label = 'make a wrapped · wrapped.devmatei.com';
  ctx.save();
  ctx.font = `600 ${Math.min(30, width * 0.06)}px Nunito`;
  const labelWidth = Math.min(width - 24, ctx.measureText(label).width + 28);
  ctx.restore();
  const x = Math.max(0, width - labelWidth - 24);
  const y = Math.max(0, height - 54);
  try {
    const pixels = ctx.getImageData(x, y, Math.max(1, Math.ceil(labelWidth)), 1).data;
    let total = 0;
    for (let index = 0; index < pixels.length; index += 4) {
      total += (0.2126 * pixels[index] + 0.7152 * pixels[index + 1] + 0.0722 * pixels[index + 2]) / 255;
    }
    return total / Math.max(1, pixels.length / 4);
  } catch {
    return 0;
  }
}

export function renderTemplate(ctx, template, { data = {}, art = null, artTransform = {}, showElements = true, watermark = true } = {}) {
  const canvas = template.canvas || DEFAULT_CANVAS;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  drawBackground(ctx, template);
  const watermarkLuminance = watermark ? sampleLuminance(ctx, template) : 0;
  drawArtwork(ctx, template, art, artTransform);
  if (showElements) {
    drawElements(ctx, template, data);
  }
  if (watermark) {
    drawWatermark(ctx, template, watermarkLuminance);
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
