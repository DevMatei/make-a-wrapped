const THEMES = {
  lavender: { name: 'lavender', background: '#15121f' },
  mint: { name: 'mint', background: '#0c1214' },
  sunset: { name: 'sunset', background: '#15110e' },
};

const STORAGE_KEY = 'wrapped-theme';

function getStoredTheme() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return THEMES[stored] ? stored : 'lavender';
  } catch {
    return 'lavender';
  }
}

function setStoredTheme(themeId) {
  try {
    localStorage.setItem(STORAGE_KEY, themeId);
  } catch {}
}

function applyTheme(themeId) {
  const id = THEMES[themeId] ? themeId : 'lavender';
  document.documentElement.dataset.theme = id;

  const favicon = document.querySelector('link[rel="icon"][type="image/svg+xml"]');
  if (favicon) {
    favicon.href = `/favicon-${id}.svg`;
  }
  const themeColor = document.querySelector('meta[name="theme-color"]');
  if (themeColor) {
    themeColor.content = THEMES[id].background;
  }
  document.querySelectorAll('[data-theme-pick]').forEach((button) => {
    button.setAttribute('aria-pressed', String(button.dataset.themePick === id));
  });
  return id;
}

export function initThemeSwitcher() {
  applyTheme(getStoredTheme());
  document.querySelectorAll('[data-theme-pick]').forEach((button) => {
    button.addEventListener('click', () => {
      setStoredTheme(applyTheme(button.dataset.themePick));
    });
  });
}

export { THEMES };
