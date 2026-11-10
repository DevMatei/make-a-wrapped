const summaryEl = document.getElementById('stats-summary');
const messageEl = document.getElementById('stats-message');
const chartEl = document.getElementById('activity-chart');
const rangeEl = document.getElementById('activity-range');
const periodButtons = [...document.querySelectorAll('[data-days]')];
const listTargets = {
  sources: document.getElementById('sources-list'),
  providers: document.getElementById('providers-list'),
  templates: document.getElementById('templates-list'),
  clients: document.getElementById('clients-list'),
};
const numberFormat = new Intl.NumberFormat();
const dateFormat = new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', timeZone: 'UTC' });
const sourceLabels = { site: 'website', api: 'api' };
const serviceLabels = { listenbrainz: 'listenbrainz', lastfm: 'last.fm', librefm: 'libre.fm', navidrome: 'navidrome' };
const clientLabels = { unidentified: 'other api clients' };
const svgNamespace = 'http://www.w3.org/2000/svg';
let activeDays = 90;
let refreshTimer;

function addSvg(name, attributes, parent = chartEl) {
  const element = document.createElementNS(svgNamespace, name);
  Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
  parent.appendChild(element);
  return element;
}

function rangeDates(days) {
  const today = new Date();
  const end = Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate());
  return Array.from({ length: days }, (_, index) => {
    const date = new Date(end - ((days - index - 1) * 86400000));
    return date.toISOString().slice(0, 10);
  });
}

function drawChart(daily, days) {
  chartEl.replaceChildren();
  const dates = rangeDates(days);
  const byDate = new Map(daily.map(({ day, count }) => [day, count]));
  const values = dates.map((day) => byDate.get(day) || 0);
  const max = Math.max(1, ...values);
  const plot = { x: 16, y: 12, width: 928, height: 178 };
  const gap = days > 180 ? 1 : 2;
  const barWidth = Math.max(1, (plot.width - (gap * (days - 1))) / days);
  const accent = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#c084fc';
  const grid = getComputedStyle(document.documentElement).getPropertyValue('--line').trim() || '#3a3150';
  [0, 0.5, 1].forEach((fraction) => {
    const y = plot.y + plot.height - plot.height * fraction;
    addSvg('line', { x1: plot.x, x2: plot.x + plot.width, y1: y, y2: y, stroke: grid, 'stroke-width': 1 });
  });
  values.forEach((value, index) => {
    const height = value ? Math.max(2, (value / max) * plot.height) : 0;
    const x = plot.x + (index * (barWidth + gap));
    const rect = addSvg('rect', {
      x,
      y: plot.y + plot.height - height,
      width: barWidth,
      height,
      rx: Math.min(3, barWidth / 2),
      fill: accent,
      opacity: value ? 0.9 : 0,
    });
    const title = addSvg('title', {}, rect);
    title.textContent = `${dates[index]}: ${numberFormat.format(value)} generations`;
  });
  const start = new Date(`${dates[0]}T00:00:00Z`);
  const end = new Date(`${dates[dates.length - 1]}T00:00:00Z`);
  rangeEl.textContent = `${dateFormat.format(start)} to ${dateFormat.format(end)} UTC`;
  const total = values.reduce((sum, count) => sum + count, 0);
  const active = values.filter((value) => value > 0).length;
  const busiestIndex = values.indexOf(Math.max(...values));
  const busiest = values[busiestIndex] ? `${dateFormat.format(new Date(`${dates[busiestIndex]}T00:00:00Z`))} · ${numberFormat.format(values[busiestIndex])}` : 'none yet';
  return { total, active, busiest };
}

function renderSummary(data, period) {
  const cards = [
    ['posters generated', data.total || 0],
    [`active days · ${period}d`, data.activity.active],
    ['busiest day', data.activity.busiest],
  ];
  summaryEl.replaceChildren();
  cards.forEach(([label, value]) => {
    const card = document.createElement('article');
    card.className = 'stats-summary__card';
    const valueEl = document.createElement('strong');
    valueEl.textContent = typeof value === 'number' ? numberFormat.format(value) : value;
    const labelEl = document.createElement('span');
    labelEl.textContent = label;
    card.append(valueEl, labelEl);
    summaryEl.appendChild(card);
  });
  summaryEl.hidden = false;
}

function renderList(target, values, labels = {}) {
  target.replaceChildren();
  const entries = Object.entries(values || {}).filter(([, count]) => count > 0).sort((a, b) => b[1] - a[1]);
  if (!entries.length) {
    const empty = document.createElement('p');
    empty.className = 'stats-list__empty';
    empty.textContent = 'no counts yet';
    target.appendChild(empty);
    return;
  }
  const max = entries[0][1];
  entries.slice(0, 8).forEach(([name, count]) => {
    const row = document.createElement('div');
    row.className = 'stats-list__row';
    const heading = document.createElement('div');
    heading.className = 'stats-list__label';
    const label = document.createElement('span');
    label.textContent = labels[name] || name.replaceAll('-', ' ');
    const value = document.createElement('strong');
    value.textContent = numberFormat.format(count);
    heading.append(label, value);
    const track = document.createElement('div');
    track.className = 'stats-list__track';
    const fill = document.createElement('span');
    fill.style.width = `${Math.max(4, (count / max) * 100)}%`;
    track.appendChild(fill);
    row.append(heading, track);
    target.appendChild(row);
  });
}

async function loadStats(days = activeDays) {
  activeDays = days;
  periodButtons.forEach((button) => button.setAttribute('aria-pressed', String(Number(button.dataset.days) === days)));
  messageEl.textContent = 'loading the numbers…';
  try {
    const response = await fetch(`/metrics/stats?days=${days}`, { cache: 'no-store' });
    if (!response.ok) {
      throw new Error(`stats request failed (${response.status})`);
    }
    const data = await response.json();
    const activity = drawChart(data.days || [], days);
    renderSummary({ ...data, activity }, days);
    renderList(listTargets.sources, data.sources, sourceLabels);
    renderList(listTargets.providers, data.generation_services, serviceLabels);
    renderList(listTargets.templates, data.templates);
    renderList(listTargets.clients, data.api_clients, clientLabels);
    messageEl.textContent = 'aggregate counts only · updates may take about a minute to sync across instances';
  } catch (error) {
    messageEl.textContent = 'stats couldn’t load right now. try again in a bit.';
    console.error(error);
  }
}

periodButtons.forEach((button) => button.addEventListener('click', () => loadStats(Number(button.dataset.days))));
loadStats();
refreshTimer = window.setInterval(() => loadStats(activeDays), 60_000);
window.addEventListener('pagehide', () => window.clearInterval(refreshTimer), { once: true });
