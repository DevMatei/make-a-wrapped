import { DEFAULT_CANVAS, fontString, normaliseTemplate, prepareBackgroundImage, renderTemplate } from './templates/engine.js';

export function createCanvasRenderer({ canvas, themeSelect, artistImg }) {
  const ctx = canvas.getContext('2d');
  let template = null;

  function setTemplate(nextTemplate) {
    template = normaliseTemplate(nextTemplate);
    prepareBackgroundImage(template);
    return template;
  }

  function getTemplate() {
    return template;
  }

  function preloadBackgrounds(callback) {
    if (!template) {
      if (typeof callback === 'function') {
        callback();
      }
      return;
    }
    prepareBackgroundImage(template, callback, callback);
  }

  function draw({ data, isCoverReady, allowTransform, imageTransform, period }) {
    if (!template) {
      return;
    }
    const art = isCoverReady && artistImg && artistImg.complete && artistImg.naturalWidth > 0 ? artistImg : null;
    const hasData = Boolean(data && data.username);
    renderTemplate(ctx, template, {
      data,
      art,
      artTransform: {
        allowTransform: Boolean(allowTransform),
        scale: imageTransform && imageTransform.scale,
        offsetX: imageTransform && imageTransform.offsetX,
        offsetY: imageTransform && imageTransform.offsetY,
      },
      showElements: hasData,
    });
  }

  function canvasSize() {
    return (template && template.canvas) || DEFAULT_CANVAS;
  }

  return {
    setTemplate,
    getTemplate,
    preloadBackgrounds,
    draw,
    canvasSize,
    get fontString() {
      return fontString;
    },
  };
}
