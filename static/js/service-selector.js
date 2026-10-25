const SERVICE_VALUES = ['listenbrainz', 'lastfm', 'librefm', 'navidrome'];

export function createServiceSelector() {
  const serviceInput = document.getElementById('service');
  const group = document.querySelector('[data-service-dropdown]');
  const radios = group ? Array.from(group.querySelectorAll('input[type="radio"]')) : [];

  function getValue() {
    return (serviceInput && serviceInput.value) || 'listenbrainz';
  }

  function getInitialValue() {
    try {
      const param = new URLSearchParams(window.location.search).get('service');
      if (param && SERVICE_VALUES.includes(param)) {
        return param;
      }
    } catch (error) {
      // ignore, fall back to the input default
    }
    return getValue();
  }

  function updateSelection(value) {
    const next = SERVICE_VALUES.includes(value) ? value : 'listenbrainz';
    radios.forEach((radio) => {
      radio.checked = radio.value === next;
    });
    if (serviceInput) {
      const previousValue = serviceInput.value;
      serviceInput.value = next;
      if (previousValue !== next) {
        serviceInput.dispatchEvent(new CustomEvent('servicechange', { detail: { value: next } }));
      }
    }
  }

  function init() {
    radios.forEach((radio) => {
      radio.addEventListener('change', () => {
        if (radio.checked) {
          updateSelection(radio.value);
        }
      });
    });
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
    withService,
  };
}
