let sampleArtPromise = null;

function drawSampleArt(seedName) {
  const size = 600;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');
  const hue = (seedName || 'Make a Wrapped').split('').reduce((sum, char) => sum + char.charCodeAt(0), 0) % 360;

  ctx.save();
  ctx.beginPath();
  ctx.roundRect(0, 0, size, size, 62);
  ctx.clip();
  const gradient = ctx.createLinearGradient(0, 0, size, size);
  gradient.addColorStop(0, `hsl(${hue}, 85%, 66%)`);
  gradient.addColorStop(0.5, `hsl(${(hue + 20) % 360}, 78%, 56%)`);
  gradient.addColorStop(1, `hsl(${(hue + 45) % 360}, 74%, 46%)`);
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, size, size);
  ctx.restore();

  const cx = size / 2;
  const cy = size / 2;
  ctx.save();
  ctx.beginPath();
  ctx.roundRect(0, 0, size, size, 62);
  ctx.clip();

  ctx.fillStyle = 'rgba(30, 27, 46, 0.92)';
  ctx.beginPath();
  ctx.arc(cx, cy, size * 0.24, 0, Math.PI * 2);
  ctx.fill();

  ctx.fillStyle = '#2a2438';
  ctx.beginPath();
  ctx.arc(cx, cy, size * 0.19, 0, Math.PI * 2);
  ctx.fill();

  ctx.strokeStyle = 'rgba(226, 232, 240, 0.22)';
  ctx.lineWidth = size * 0.008;
  [0.10, 0.15, 0.20].forEach((r) => {
    ctx.beginPath();
    ctx.arc(cx, cy, size * r, 0, Math.PI * 2);
    ctx.stroke();
  });

  ctx.fillStyle = '#e9d5ff';
  ctx.beginPath();
  ctx.arc(cx, cy, size * 0.035, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
  return canvas;
}

function canvasToImage(canvas) {
  return new Promise((resolve) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => resolve(null);
    image.src = canvas.toDataURL('image/png');
  });
}

export function getSampleArt() {
  if (sampleArtPromise) {
    return sampleArtPromise;
  }
  sampleArtPromise = canvasToImage(drawSampleArt('Make a Wrapped'));
  return sampleArtPromise;
}

export function isSampleArtReady() {
  return Boolean(sampleArtPromise);
}
