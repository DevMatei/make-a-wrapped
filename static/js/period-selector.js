const PERIOD_STORAGE_KEY = 'wrappedPeriodSelection';
const PERIOD_PRESET_VALUES = new Set([
  'this_year',
  'last_year',
  'last_12_months',
  'this_month',
  'last_month',
  'specific_month',
  'all_time',
]);

const SPECIFIC_MONTH_VALUE = 'specific_month';

function clone(value) {
  if (typeof structuredClone === 'function') {
    return structuredClone(value);
  }
  return JSON.parse(JSON.stringify(value));
}

function previousMonth() {
  const now = new Date();
  const prev = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - 1, 1));
  return { month: prev.getUTCMonth() + 1, year: prev.getUTCFullYear() };
}

function maxMonthFrom(descriptor) {
  const max = descriptor && descriptor.maxSpecificMonth;
  if (max && Number.isFinite(Number(max.month)) && Number.isFinite(Number(max.year))) {
    return { month: Number(max.month), year: Number(max.year) };
  }
  const now = new Date();
  return { month: now.getUTCMonth() + 1, year: now.getUTCFullYear() };
}

function isFinishedMonth(month, year, descriptor) {
  const max = maxMonthFrom(descriptor);
  return year < max.year || (year === max.year && month < max.month);
}

function defaultFromDescriptor(descriptor) {
  const preset = descriptor && descriptor.defaults && descriptor.defaults.preset;
  return {
    preset: PERIOD_PRESET_VALUES.has(preset) ? preset : 'this_year',
    month: null,
    year: null,
  };
}

function readStored() {
  try {
    const raw = window.localStorage.getItem(PERIOD_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return null;
    if (!PERIOD_PRESET_VALUES.has(parsed.preset)) return null;
    return parsed;
  } catch (error) {
    return null;
  }
}

function writeStored(selection) {
  try {
    window.localStorage.setItem(PERIOD_STORAGE_KEY, JSON.stringify(selection));
  } catch (error) {
  }
}

function buildQueryString(selection) {
  if (!selection || !selection.preset) return '';
  const params = new URLSearchParams();
  params.set('range', selection.preset);
  if (selection.preset === SPECIFIC_MONTH_VALUE) {
    if (selection.month) params.set('month', String(selection.month));
    if (selection.year) params.set('year', String(selection.year));
  }
  return params.toString();
}

function validateSelection(selection, descriptor) {
  if (!selection || !PERIOD_PRESET_VALUES.has(selection.preset)) {
    return defaultFromDescriptor(descriptor);
  }
  if (selection.preset !== SPECIFIC_MONTH_VALUE) {
    return { preset: selection.preset, month: null, year: null };
  }
  const month = Number(selection.month);
  const year = Number(selection.year);
  const valid = Number.isInteger(month) && month >= 1 && month <= 12
    && Number.isInteger(year) && year >= 1970
    && isFinishedMonth(month, year, descriptor);
  if (!valid) {
    return { preset: SPECIFIC_MONTH_VALUE, ...previousMonth() };
  }
  return { preset: SPECIFIC_MONTH_VALUE, month, year };
}

export function createPeriodSelector({ descriptor, onChange } = {}) {
  const select = document.getElementById('period-select');
  const specificGroup = document.querySelector('[data-period-specific]');
  const monthSelect = document.getElementById('period-specific-month');
  const yearSelect = document.getElementById('period-specific-year');

  let _descriptor = descriptor || null;
  let current = defaultFromDescriptor(_descriptor);

  function emit() {
    if (onChange) onChange(clone(current));
  }

  function getSelection() {
    return clone(current);
  }

  function withRange(path) {
    if (!path) return path;
    const query = buildQueryString(current);
    if (!query) return path;
    const separator = path.includes('?') ? '&' : '?';
    return `${path}${separator}${query}`;
  }

  function monthEntries() {
    if (_descriptor && Array.isArray(_descriptor.months) && _descriptor.months.length) {
      return _descriptor.months.map((entry) => ({ value: Number(entry.value), label: String(entry.label).toLowerCase() }));
    }
    return Array.from({ length: 12 }, (_, i) => ({
      value: i + 1,
      label: new Date(2000, i, 1).toLocaleString(undefined, { month: 'long' }).toLowerCase(),
    }));
  }

  function yearEntries() {
    const max = maxMonthFrom(_descriptor);
    const years = _descriptor && Array.isArray(_descriptor.years) && _descriptor.years.length
      ? _descriptor.years.map(Number)
      : Array.from({ length: 10 }, (_, i) => max.year - i);
    return years.filter((year) => year < max.year || (year === max.year && max.month > 1));
  }

  function fillOptions(target, entries, selected) {
    target.replaceChildren(...entries.map((entry) => {
      const option = document.createElement('option');
      option.value = String(entry.value);
      option.textContent = entry.label;
      return option;
    }));
    target.value = String(selected);
  }

  function renderSpecific() {
    if (!specificGroup) return;
    const visible = current.preset === SPECIFIC_MONTH_VALUE;
    specificGroup.hidden = !visible;
    if (!visible || !monthSelect || !yearSelect) return;
    const years = yearEntries();
    fillOptions(yearSelect, years.map((year) => ({ value: year, label: String(year) })), current.year);
    const months = monthEntries().filter((entry) => isFinishedMonth(entry.value, current.year, _descriptor));
    fillOptions(monthSelect, months, current.month);
  }

  function applySelection(selection) {
    current = validateSelection(selection, _descriptor);
    if (select) select.value = current.preset;
    renderSpecific();
    writeStored(current);
  }

  function init(desc) {
    if (desc) _descriptor = desc;
    if (!select) return;
    applySelection(readStored() || defaultFromDescriptor(_descriptor));

    select.addEventListener('change', () => {
      const preset = select.value;
      if (!PERIOD_PRESET_VALUES.has(preset)) return;
      const next = preset === SPECIFIC_MONTH_VALUE
        ? { preset, month: current.month, year: current.year }
        : { preset };
      applySelection(next);
      emit();
    });

    if (monthSelect) {
      monthSelect.addEventListener('change', () => {
        applySelection({ ...current, month: Number(monthSelect.value) });
        emit();
      });
    }
    if (yearSelect) {
      yearSelect.addEventListener('change', () => {
        const year = Number(yearSelect.value);
        let month = current.month;
        if (!isFinishedMonth(month, year, _descriptor)) {
          month = maxMonthFrom(_descriptor).month - 1;
        }
        applySelection({ ...current, year, month });
        emit();
      });
    }
  }

  return {
    init,
    getSelection,
    withRange,
    applySelection,
  };
}

export async function loadPeriodDescriptor() {
  try {
    const response = await fetch('/api/period-options', { cache: 'no-store' });
    if (!response.ok) throw new Error(`status ${response.status}`);
    return await response.json();
  } catch (error) {
    return {
      presets: [
        { value: 'this_year', label: 'This year', kind: 'year' },
        { value: 'last_year', label: 'Last year', kind: 'year' },
        { value: 'last_12_months', label: 'Last 12 months', kind: 'year' },
        { value: 'this_month', label: 'This month', kind: 'month' },
        { value: 'last_month', label: 'Last month', kind: 'month' },
        { value: 'specific_month', label: 'Specific month', kind: 'month' },
        { value: 'all_time', label: 'All time', kind: 'year' },
      ],
      months: Array.from({ length: 12 }, (_, i) => ({
        value: String(i + 1),
        label: new Date(2000, i, 1).toLocaleString(undefined, { month: 'long' }),
      })),
      years: Array.from({ length: 10 }, (_, i) => new Date().getUTCFullYear() - i),
      defaults: {
        preset: 'this_year',
        month: new Date().getUTCMonth() + 1,
        year: new Date().getUTCFullYear(),
      },
      maxSpecificMonth: {
        month: new Date().getUTCMonth() + 1,
        year: new Date().getUTCFullYear(),
      },
    };
  }
}
