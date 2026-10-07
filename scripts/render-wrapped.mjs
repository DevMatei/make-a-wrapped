import { createCanvas, GlobalFonts, loadImage, SvgExportFlag } from '@napi-rs/canvas';
import { normaliseTemplate, renderTemplate } from '../static/js/templates/engine.js';
import { paintSampleArt } from '../static/js/templates/sample-art.js';

const MAX_CANVAS_PIXELS = 2_500_000;
const MAX_OUTPUT_BYTES = 12 * 1024 * 1024;
const SAMPLE_ART_SIZE = 600;

async function sampleArtImage() {
  const canvas = createCanvas(SAMPLE_ART_SIZE, SAMPLE_ART_SIZE);
  paintSampleArt(canvas.getContext('2d'), SAMPLE_ART_SIZE, 'Make a Wrapped');
  return loadImage(canvas.toBuffer('image/png'));
}

function downscale(canvas, width, height, outputWidth) {
  if (!Number.isInteger(outputWidth) || outputWidth < 1 || outputWidth >= width) {
    return canvas;
  }
  const outputHeight = Math.max(1, Math.round((height * outputWidth) / width));
  const scaled = createCanvas(outputWidth, outputHeight);
  const ctx = scaled.getContext('2d');
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(canvas, 0, 0, outputWidth, outputHeight);
  return scaled;
}

async function readInput() {
  const chunks = [];
  for await (const chunk of process.stdin) {
    chunks.push(chunk);
  }
  return JSON.parse(Buffer.concat(chunks).toString('utf8'));
}

async function render() {
  const input = await readInput();
  const template = normaliseTemplate(input.template);
  const { width, height } = template.canvas;
  if (
    !Number.isInteger(width)
    || !Number.isInteger(height)
    || width < 1
    || height < 1
    || width * height > MAX_CANVAS_PIXELS
  ) {
    throw new Error('Template canvas exceeds the render size limit.');
  }

  const assets = input.assets || {};
  const background = assets.background ? await loadImage(Buffer.from(assets.background, 'base64')) : null;
  let artwork = assets.artwork ? await loadImage(Buffer.from(assets.artwork, 'base64')) : null;
  if (!artwork && input.sampleArt) {
    artwork = await sampleArtImage();
  }
  if (background) {
    template.background._image = background;
  }

  const isSvg = input.format === 'svg';
  const canvas = isSvg
    ? createCanvas(width, height, SvgExportFlag.ConvertTextToPaths)
    : createCanvas(width, height);

  GlobalFonts.registerFromPath('./static/font/Nunito-Regular.ttf', 'Nunito');
  GlobalFonts.registerFromPath('./static/font/Nunito-Bold.ttf', 'Nunito');

  renderTemplate(canvas.getContext('2d'), template, {
    data: input.data,
    art: artwork,
    showElements: true,
  });

  const output = isSvg
    ? canvas.getContent()
    : downscale(canvas, width, height, input.outputWidth).toBuffer('image/png');
  if (output.length > MAX_OUTPUT_BYTES) {
    throw new Error('Generated image exceeds the output size limit.');
  }
  process.stdout.write(output);
}

render().catch((error) => {
  process.stderr.write(`${error.message || 'Rendering failed.'}\n`);
  process.exitCode = 1;
});
