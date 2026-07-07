const THEMES = [
  {
    name: 'lavender chill',
    id: 'lavender',
    colors: {
      primary: '#c084fc',
      secondary: '#a855f7',
      background: '#1e1b2e',
      surface: '#2a2438',
      text: '#e2e8f0',
      textSecondary: '#94a3b8',
      border: '#3f3851',
    },
  },
  {
    name: 'mint breeze',
    id: 'mint',
    colors: {
      primary: '#6ee7b7',
      secondary: '#34d399',
      background: '#0f1419',
      surface: '#1a202c',
      text: '#e2e8f0',
      textSecondary: '#94a3b8',
      border: '#2d3748',
    },
  },
  {
    name: 'sunset glow',
    id: 'sunset',
    colors: {
      primary: '#fbbf24',
      secondary: '#f59e0b',
      background: '#1c1917',
      surface: '#292524',
      text: '#e2e8f0',
      textSecondary: '#94a3b8',
      border: '#44403c',
    },
  },
];

function getStoredTheme() {
  try {
    return localStorage.getItem('wrapped-theme') || 'lavender';
  } catch {
    return 'lavender';
  }
}

function setStoredTheme(themeId) {
  try {
    localStorage.setItem('wrapped-theme', themeId);
  } catch {}
}

function applyTheme(themeId) {
  const theme = THEMES.find((t) => t.id === themeId) || THEMES[0];
  const root = document.documentElement;

  root.style.setProperty('--bg', theme.colors.background);
  root.style.setProperty('--bg-accent', theme.colors.surface);
  root.style.setProperty('--card', `${theme.colors.surface}f2`);
  root.style.setProperty('--card-border', theme.colors.border);
  root.style.setProperty('--text', theme.colors.text);
  root.style.setProperty('--text-muted', theme.colors.textSecondary);
  root.style.setProperty('--accent', theme.colors.primary);
  root.style.setProperty('--accent-strong', theme.colors.secondary);
  root.style.setProperty('--accent-soft', `${theme.colors.primary}33`);

  document.body.style.backgroundColor = theme.colors.background;
  document.body.style.backgroundImage = `
    radial-gradient(ellipse at 20% 0%, ${theme.colors.primary}26 0%, transparent 50%),
    radial-gradient(ellipse at 80% 100%, ${theme.colors.secondary}1a 0%, transparent 50%)
  `;

  updateFavicon(themeId);
  setStoredTheme(themeId);

  document.querySelectorAll('.theme-bar__btn').forEach((btn) => {
    btn.classList.toggle('is-active', btn.dataset.theme === themeId);
  });
}

function updateFavicon(themeId) {
  const faviconLink = document.querySelector('link[rel="icon"][type="image/svg+xml"]');
  if (faviconLink) {
    faviconLink.href = `favicon-${themeId}.svg`;
  }
}

function createThemeBar() {
  const h1 = document.querySelector('.card--intro h1');
  if (!h1) return;

  const bar = document.createElement('div');
  bar.className = 'theme-bar';
  bar.innerHTML = `
    <span class="theme-bar__label">Theme</span>
    <div class="theme-bar__options">
      ${THEMES.map((theme) => `
        <button
          type="button"
          class="theme-bar__btn${theme.id === getStoredTheme() ? ' is-active' : ''}"
          data-theme="${theme.id}"
          title="${theme.name}"
          aria-label="${theme.name}"
        ></button>
      `).join('')}
    </div>
  `;

  h1.insertAdjacentElement('afterend', bar);

  bar.querySelectorAll('.theme-bar__btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      applyTheme(btn.dataset.theme);
    });
  });
}

export function initThemeSwitcher() {
  const storedTheme = getStoredTheme();
  applyTheme(storedTheme);
  createThemeBar();
}

export { THEMES };
