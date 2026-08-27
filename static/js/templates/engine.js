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
      contain: artwork.contain !== false,
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
  const containScale = config.contain ? Math.min(destSize / imgWidth, destSize / imgHeight) : 1;
  const transform = artTransform || {};
  const scale = transform.allowTransform && Number.isFinite(transform.scale) ? transform.scale : 1;
  const offsetX = transform.allowTransform && Number.isFinite(transform.offsetX) ? transform.offsetX : 0;
  const offsetY = transform.allowTransform && Number.isFinite(transform.offsetY) ? transform.offsetY : 0;

  const drawWidth = imgWidth * containScale * scale;
  const drawHeight = imgHeight * containScale * scale;
  const drawX = destX + (destSize - drawWidth) / 2 + offsetX;
  const drawY = destY + (destSize - drawHeight) / 2 + offsetY;
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

export function renderTemplate(ctx, template, { data = {}, art = null, artTransform = {}, showElements = true } = {}) {
  const canvas = template.canvas || DEFAULT_CANVAS;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  drawBackground(ctx, template);
  drawArtwork(ctx, template, art, artTransform);
  if (showElements) {
    drawElements(ctx, template, data);
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
