import { SERVICE_LABELS } from './constants.js';

function getServiceLabel(key) {
  if (SERVICE_LABELS[key]) {
    return SERVICE_LABELS[key];
  }
  return key ? `${key.charAt(0).toUpperCase()}${key.slice(1)}` : 'Make a Wrapped';
}

export function createServiceSelector() {
  const serviceInput = document.getElementById('service');
  const serviceDropdown = document.querySelector('[data-service-dropdown]');
  const serviceToggle = serviceDropdown ? serviceDropdown.querySelector('[data-dropdown-toggle]') : null;
  const serviceMenu = serviceDropdown ? serviceDropdown.querySelector('[data-dropdown-menu]') : null;
  const serviceOptions = serviceDropdown ? Array.from(serviceDropdown.querySelectorAll('[data-dropdown-option]')) : [];
  const serviceCurrentLabel = serviceDropdown ? serviceDropdown.querySelector('.service-select__current') : null;

  function getValue() {
    return (serviceInput && serviceInput.value) || 'listenbrainz';
  }

  function getInitialValue() {
    try {
      const param = new URLSearchParams(window.location.search).get('service');
      if (param && serviceOptions.some((option) => option.dataset.value === param)) {
        return param;
      }
    } catch (error) {
      // ignore, fall back to the input default
    }
    return getValue();
  }

  function updateSelection(value, labelText) {
    if (!serviceDropdown) {
      return;
    }
    if (serviceInput) {
      const previousValue = serviceInput.value;
      serviceInput.value = value;
      if (previousValue !== value) {
        serviceInput.dispatchEvent(new CustomEvent('servicechange', { detail: { value } }));
      }
    }
    if (serviceCurrentLabel) {
      serviceCurrentLabel.textContent = labelText || getServiceLabel(value);
    }
    serviceOptions.forEach((option) => {
      const isActive = option.dataset.value === value && option.getAttribute('aria-disabled') !== 'true';
      option.classList.toggle('is-active', isActive);
      option.setAttribute('aria-selected', String(isActive));
    });
  }

  function openDropdown() {
    if (!serviceDropdown) {
      return;
    }
    serviceDropdown.classList.add('is-open');
    if (serviceToggle) {
      serviceToggle.setAttribute('aria-expanded', 'true');
    }
    if (serviceMenu) {
      serviceMenu.setAttribute('aria-hidden', 'false');
    }
  }

  function closeDropdown() {
    if (!serviceDropdown) {
      return;
    }
    serviceDropdown.classList.remove('is-open');
    if (serviceToggle) {
      serviceToggle.setAttribute('aria-expanded', 'false');
    }
    if (serviceMenu) {
      serviceMenu.setAttribute('aria-hidden', 'true');
    }
  }

  function toggleDropdown() {
    if (!serviceDropdown) {
      return;
    }
    if (serviceDropdown.classList.contains('is-open')) {
      closeDropdown();
    } else {
      openDropdown();
    }
  }

  function init() {
    if (!serviceDropdown) {
      return;
    }
    if (serviceToggle) {
      serviceToggle.addEventListener('click', (event) => {
        event.stopPropagation();
        toggleDropdown();
      });
    }
    serviceOptions.forEach((option) => {
      option.addEventListener('click', (event) => {
        event.stopPropagation();
        if (
          option.classList.contains('service-select__option--disabled')
          || option.getAttribute('aria-disabled') === 'true'
        ) {
          return;
        }
        const value = option.dataset.value || 'listenbrainz';
        const label = option.dataset.label || getServiceLabel(value);
        updateSelection(value, label);
        closeDropdown();
      });
    });
    document.addEventListener('click', (event) => {
      if (serviceDropdown && !serviceDropdown.contains(event.target)) {
        closeDropdown();
      }
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        closeDropdown();
      }
    });
    if (serviceMenu) {
      serviceMenu.setAttribute('aria-hidden', 'true');
    }
    updateSelection(getInitialValue());
  }

  function withService(path) {
    const service = getValue();
    if (!service) {
      return path;
    }
    const separator = path.includes('?') ? '&' : '?';
    return `${path}${separator}service=${encodeURIComponent(service)}`;
  }

  return {
    init,
    getValue,
    updateSelection,
    closeDropdown,
    withService,
  };
}
