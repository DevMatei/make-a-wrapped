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

const FALLBACK_RANGE = { preset: 'this_year', month: null, year: null };
const SPECIFIC_MONTH_VALUE = 'specific_month';

function clone(value) {
  if (typeof structuredClone === 'function') {
    return structuredClone(value);
  }
  return JSON.parse(JSON.stringify(value));
}

function defaultFromDescriptors(descriptor) {
  const fallback = descriptor && descriptor.defaults ? descriptor.defaults : null;
  if (!fallback) {
    return { ...FALLBACK_RANGE };
  }
  return {
    preset: fallback.preset || FALLBACK_RANGE.preset,
    month: fallback.month || null,
    year: fallback.year || null,
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
  if (!selection) return defaultFromDescriptors(descriptor);
  const safe = defaultFromDescriptors(descriptor);
  if (!PERIOD_PRESET_VALUES.has(selection.preset)) {
    return safe;
  }
  safe.preset = selection.preset;
  if (selection.preset === SPECIFIC_MONTH_VALUE) {
    const month = Number(selection.month);
    const year = Number(selection.year);
    if (!Number.isFinite(month) || month < 1 || month > 12) {
      return safe;
    }
    if (!Number.isFinite(year) || year < 1970 || year > 9999) {
      return safe;
    }
    const max = descriptor && descriptor.maxSpecificMonth;
    if (max) {
      const maxYear = Number(max.year);
      const maxMonth = Number(max.month);
      if (year > maxYear || (year === maxYear && month >= maxMonth)) {
        safe.month = maxMonth;
        safe.year = maxYear;
      } else {
        safe.month = month;
        safe.year = year;
      }
    } else {
      safe.month = month;
      safe.year = year;
    }
  }
  return safe;
}

export function createPeriodSelector({ descriptor, onChange } = {}) {
  const dropdown = document.querySelector('[data-period-dropdown]');
  const toggle = dropdown ? dropdown.querySelector('[data-period-toggle]') : null;
  const menu = dropdown ? dropdown.querySelector('[data-period-menu]') : null;
  const options = dropdown
    ? Array.from(dropdown.querySelectorAll('[data-period-option]'))
    : [];
  const currentLabel = dropdown ? dropdown.querySelector('.period-select__current') : null;
  const specificGroup = document.querySelector('[data-period-specific]');
  const specificMonthSelect = document.getElementById('period-specific-month');
  const specificYearSelect = document.getElementById('period-specific-year');

  let _descriptor = descriptor || null;
  let current = defaultFromDescriptors(_descriptor);

  function emit() {
    const snapshot = clone(current);
    if (onChange) onChange(snapshot);
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

  function updateLabel() {
    if (!currentLabel) return;
    if (current.preset === SPECIFIC_MONTH_VALUE && current.month && current.year) {
      const monthName = specificMonthSelect
        ? specificMonthSelect.options[specificMonthSelect.selectedIndex]?.text
        : '';
      const label = monthName ? `${monthName} ${current.year}` : `${current.month}/${current.year}`;
      currentLabel.textContent = label;
    } else {
      const presetLabel = options.find((opt) => opt.dataset.value === current.preset)?.dataset.label
        || current.preset;
      currentLabel.textContent = presetLabel;
    }
  }

  function populateSpecificSelectors() {
    if (!specificMonthSelect || !specificYearSelect || !_descriptor) return;
    if (!specificMonthSelect.options.length) {
      _descriptor.months.forEach((entry) => {
        const opt = document.createElement('option');
        opt.value = entry.value;
        opt.textContent = entry.label;
        specificMonthSelect.appendChild(opt);
      });
    }
    if (!specificYearSelect.options.length) {
      _descriptor.years.forEach((year) => {
        const opt = document.createElement('option');
        opt.value = String(year);
        opt.textContent = String(year);
        specificYearSelect.appendChild(opt);
      });
    }
  }

  function refreshSpecificVisibility() {
    if (!specificGroup) return;
    const visible = current.preset === SPECIFIC_MONTH_VALUE;
    specificGroup.classList.toggle('is-visible', visible);
    if (visible) {
      populateSpecificSelectors();
      if (specificMonthSelect) {
        specificMonthSelect.value = current.month ? String(current.month) : String(_descriptor?.defaults?.month || 1);
      }
      if (specificYearSelect) {
        specificYearSelect.value = current.year ? String(current.year) : String(_descriptor?.defaults?.year || new Date().getUTCFullYear());
      }
      if (specificMonthSelect && current.month) specificMonthSelect.value = String(current.month);
      if (specificYearSelect && current.year) specificYearSelect.value = String(current.year);
      updateSpecificMax();
    }
  }

  function updateSpecificMax() {
    if (!specificMonthSelect || !specificYearSelect || !_descriptor?.maxSpecificMonth) return;
    const maxYear = Number(_descriptor.maxSpecificMonth.year);
    const maxMonth = Number(_descriptor.maxSpecificMonth.month);
    Array.from(specificYearSelect.options).forEach((opt) => {
      const year = Number(opt.value);
      if (year > maxYear) {
        opt.disabled = true;
      } else {
        opt.disabled = false;
      }
    });
    Array.from(specificMonthSelect.options).forEach((opt) => {
      const month = Number(opt.value);
      const selectedYear = Number(specificYearSelect.value);
      if (selectedYear >= maxYear && month >= maxMonth) {
        opt.disabled = true;
      } else {
        opt.disabled = false;
      }
    });
  }

  function applySelection(selection) {
    current = validateSelection(selection, _descriptor);
    options.forEach((opt) => {
      const active = opt.dataset.value === current.preset;
      opt.classList.toggle('is-active', active);
      opt.setAttribute('aria-selected', String(active));
    });
    refreshSpecificVisibility();
    updateLabel();
    writeStored(current);
  }

  function openDropdown() {
    if (!dropdown) return;
    dropdown.classList.add('is-open');
    if (toggle) toggle.setAttribute('aria-expanded', 'true');
    if (menu) menu.setAttribute('aria-hidden', 'false');
  }

  function closeDropdown() {
    if (!dropdown) return;
    dropdown.classList.remove('is-open');
    if (toggle) toggle.setAttribute('aria-expanded', 'false');
    if (menu) menu.setAttribute('aria-hidden', 'true');
  }

  function toggleDropdown() {
    if (!dropdown) return;
    if (dropdown.classList.contains('is-open')) {
      closeDropdown();
    } else {
      openDropdown();
    }
  }

  function init(desc) {
    if (desc) _descriptor = desc;
    if (!dropdown) return;
    populateSpecificSelectors();
    const stored = readStored();
    applySelection(stored || defaultFromDescriptors(_descriptor));

    if (toggle) {
      toggle.addEventListener('click', (event) => {
        event.stopPropagation();
        toggleDropdown();
      });
    }

    options.forEach((opt) => {
      opt.addEventListener('click', (event) => {
        event.stopPropagation();
        const value = opt.dataset.value;
        if (!value || !PERIOD_PRESET_VALUES.has(value)) return;
        const next = { ...current, preset: value };
        if (value !== SPECIFIC_MONTH_VALUE) {
          next.month = null;
          next.year = null;
        } else if (!next.month || !next.year) {
          next.month = _descriptor?.defaults?.month || null;
          next.year = _descriptor?.defaults?.year || null;
        }
        applySelection(next);
        closeDropdown();
        emit();
      });
    });

    document.addEventListener('click', (event) => {
      if (dropdown && !dropdown.contains(event.target)) {
        closeDropdown();
      }
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') closeDropdown();
    });

    if (specificMonthSelect) {
      specificMonthSelect.addEventListener('change', () => {
        const next = { ...current, month: Number(specificMonthSelect.value) };
        applySelection(next);
        emit();
      });
    }
    if (specificYearSelect) {
      specificYearSelect.addEventListener('change', () => {
        const next = { ...current, year: Number(specificYearSelect.value) };
        applySelection(next);
        updateSpecificMax();
        emit();
      });
    }

    if (menu) menu.setAttribute('aria-hidden', 'true');
  }

  return {
    init,
    getSelection,
    withRange,
    applySelection,
    closeDropdown,
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
