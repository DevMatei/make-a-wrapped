import { BACKGROUND_SOURCES, THEME_COLORS } from './constants.js';
import { normaliseGenreLabel } from './utils.js';

function getPalette(theme) {
  return THEME_COLORS[theme] || THEME_COLORS.black;
}

export function createCanvasRenderer({ canvas, themeSelect, artistImg }) {
  const ctx = canvas.getContext('2d');
  const backgrounds = {};
  const leftColumnX = 112;
  const rightColumnX = 590;
  const columnGap = 24;
  const rightPadding = 112;
  const leftColumnWidth = Math.max(0, rightColumnX - leftColumnX - columnGap);
  const rightColumnWidth = Math.max(0, canvas.width - rightColumnX - rightPadding);

  function preloadBackgrounds(callback) {
    Object.entries(BACKGROUND_SOURCES).forEach(([key, src]) => {
      const image = new Image();
      image.src = src;
      image.onload = () => {
        if (key === themeSelect.value && typeof callback === 'function') {
          callback();
        }
      };
      backgrounds[key] = image;
    });
  }

  function ellipsizeText(text, maxWidth) {
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

  function formatListEntry(item, index, maxWidth) {
    const prefix = `${index + 1}. `;
    const value = typeof item === 'string' ? item : '';
    if (!maxWidth || maxWidth <= 0) {
      return `${prefix}${value}`;
    }
    const prefixWidth = ctx.measureText(prefix).width;
    const availableWidth = Math.max(0, maxWidth - prefixWidth);
    const truncated = ellipsizeText(value, availableWidth);
    return `${prefix}${truncated}`;
  }

  function drawList(items, x, startY, color, maxWidth) {
    const lineHeight = 72;
    ctx.fillStyle = color;
    const list = Array.isArray(items) ? items : [];
    list.forEach((item, index) => {
      const label = formatListEntry(item, index, maxWidth);
      ctx.fillText(label, x, startY + index * lineHeight);
    });
  }

  function fitTextWithFont(text, {
    fontWeight = '700',
    fontSize = 68,
    fontFamily = 'Nunito',
    maxWidth,
    minFontSize = 40,
    ellipsize = true,
  } = {}) {
    let size = fontSize;
    let value = typeof text === 'string' ? text : '';
    ctx.save();
    ctx.font = `${fontWeight} ${size}px ${fontFamily}`;
    if (maxWidth && maxWidth > 0) {
      while (size > minFontSize && ctx.measureText(value).width > maxWidth) {
        size -= 2;
        ctx.font = `${fontWeight} ${size}px ${fontFamily}`;
      }
      if (ctx.measureText(value).width > maxWidth && ellipsize) {
        value = ellipsizeText(value, maxWidth);
      }
    }
    ctx.restore();
    return {
      text: value,
      font: `${fontWeight} ${size}px ${fontFamily}`,
    };
  }

  function draw({ data, isCoverReady, customArtworkActive, imageTransform, period }) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const theme = themeSelect.value;
    const background = backgrounds[theme];
    if (background && background.complete) {
      ctx.drawImage(background, 0, 0, canvas.width, canvas.height);
    } else if (background) {
      background.onload = () => draw({
        data,
        isCoverReady,
        customArtworkActive,
        imageTransform,
      });
    }

    if (!data) {
      return;
    }

    if (isCoverReady && artistImg.complete && artistImg.naturalWidth > 0) {
      const isBlackNew = theme === 'black_new';
      const isWhiteNew = theme === 'white_new';
      const isNewTemplate = isBlackNew || isWhiteNew;
      const destX = isNewTemplate ? 217 : 268;  
      const destY = isNewTemplate ? 70 : 244;  
      const destSize = isNewTemplate ? 780 : 544;
      const imgWidth = artistImg.naturalWidth;
      const imgHeight = artistImg.naturalHeight;
      const containScale = Math.min(destSize / imgWidth, destSize / imgHeight);
      const allowTransform = customArtworkActive;
      const userScale = allowTransform && Number.isFinite(imageTransform.scale) ? imageTransform.scale : 1;
      const offsetX = allowTransform && Number.isFinite(imageTransform.offsetX) ? imageTransform.offsetX : 0;
      const offsetY = allowTransform && Number.isFinite(imageTransform.offsetY) ? imageTransform.offsetY : 0;

      const drawWidth = imgWidth * containScale * userScale;
      const drawHeight = imgHeight * containScale * userScale;
      const drawX = destX + (destSize - drawWidth) / 2 + offsetX;
      const drawY = destY + (destSize - drawHeight) / 2 + offsetY;

      ctx.save();
      ctx.beginPath();
      if (typeof ctx.roundRect === 'function') {
        ctx.roundRect(destX, destY, destSize, destSize, 32);
      } else {
        ctx.rect(destX, destY, destSize, destSize);
      }
      ctx.clip();
      ctx.drawImage(artistImg, 0, 0, imgWidth, imgHeight, drawX, drawY, drawWidth, drawHeight);
      ctx.restore();

      ctx.save();
      const frameGradient = ctx.createLinearGradient(destX, destY, destX, destY + destSize);
      frameGradient.addColorStop(0, 'rgba(5, 8, 16, 0.55)');
      frameGradient.addColorStop(1, 'rgba(5, 8, 16, 0.25)');
      ctx.strokeStyle = frameGradient;
      ctx.lineWidth = 10;
      ctx.strokeRect(destX + 5, destY + 5, destSize - 10, destSize - 10);
      ctx.restore();
    }

    const palette = getPalette(theme);
    const isNewTemplate = theme === 'black_new' || theme === 'white_new';
    const listHeadingY = 1080;
    const listStartY = 1180;
    const summaryLabelY = 1700;
    const summaryValueY = 1775;

    ctx.fillStyle = palette.label;
    ctx.textBaseline = 'top';

    const headingFont = isNewTemplate ? '600 48px Nunito' : '400 40px Nunito';
    const listItemFont = isNewTemplate ? '800 48px Nunito' : '700 40px Nunito';
    const labelFont = isNewTemplate ? '600 48px Nunito' : '400 40px Nunito';
    const valueFont = isNewTemplate ? '800 80px Nunito' : '700 68px Nunito';

    ctx.font = headingFont;
    ctx.fillText('Top Artists', leftColumnX, listHeadingY);
    ctx.fillText('Top Tracks', rightColumnX, listHeadingY);

    const artistList = Array.isArray(data.artists) ? data.artists : [];
    const trackList = Array.isArray(data.tracks) ? data.tracks : [];
    ctx.font = listItemFont;
    drawList(artistList, leftColumnX, listStartY, palette.value, leftColumnWidth);
    drawList(trackList, rightColumnX, listStartY, palette.value, rightColumnWidth);

    ctx.font = labelFont;
    ctx.fillStyle = palette.label;
    ctx.fillText('Minutes Listened', leftColumnX, summaryLabelY);
    ctx.fillText('Top Genre', rightColumnX, summaryLabelY);

    ctx.font = valueFont;
    ctx.fillStyle = palette.value;
    const minutesLabel = typeof data.minutes === 'string' ? data.minutes : '0';
    const minutesLayout = fitTextWithFont(minutesLabel, {
      maxWidth: leftColumnWidth,
      minFontSize: isNewTemplate ? 50 : 44,
      ellipsize: true,
      fontWeight: isNewTemplate ? '800' : '700',
      fontSize: isNewTemplate ? 80 : 68,
    });
    ctx.font = minutesLayout.font;
    ctx.fillText(minutesLayout.text, leftColumnX, summaryValueY);

    const genreLabel = normaliseGenreLabel(data.genre);
    const genreLayout = fitTextWithFont(genreLabel, {
      maxWidth: rightColumnWidth,
      ellipsize: true,
      fontWeight: isNewTemplate ? '800' : '700',
      fontSize: isNewTemplate ? 80 : 68,
    });
    ctx.font = genreLayout.font;
    ctx.fillText(genreLayout.text, rightColumnX, summaryValueY);
  }

  return {
    preloadBackgrounds,
    draw,
  };
}
