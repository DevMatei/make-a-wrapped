import {
  ALL_SECTIONS,
  ARTWORK_STORAGE_KEY,
  ARTWORK_TRANSFORM_KEY,
  ARTWORK_TOKEN_KEY,
  ARTWORK_TOKEN_EXPIRY_KEY,
  ARTWORK_SOURCE_KEY,
  BACKGROUND_SOURCES,
  TURNSTILE_TOKEN_KEY,
  TURNSTILE_TOKEN_EXPIRY_KEY,
  TURNSTILE_TOKEN_TTL_MS,
  COUNTER_REFRESH_INTERVAL,
  MAX_ARTWORK_BYTES,
  SERVICE_LABELS,
} from './constants.js';
import { createCanvasRenderer } from './canvas-renderer.js';
import { createServiceSelector } from './service-selector.js';
import { NavidromeClient } from './navidrome-client.js';
import {
  formatSectionListForStatus,
  parseSectionSelection,
  formatRankedList,
  sanitiseRankedArray,
  normaliseGenreLabel,
  ensureMinutesLabel,
  loadImage,
  readFileAsDataUrl,
} from './utils.js';
import {
  readLocal,
  writeLocal,
  removeLocal,
  readSession,
  writeSession,
  removeSession,
} from './storage.js';

const canvas = document.getElementById('canvas');
const themeSelect = document.getElementById('color');
const form = document.getElementById('wrapped-form');
const usernameField = document.getElementById('username');
const navidromeUsernameInput = document.getElementById('navidrome-username');
const usernameLabel = document.getElementById('username-label');
const serviceHiddenInput = document.getElementById('service');
const turnstileWrapper = document.getElementById('turnstile-wrapper');
const turnstileContainer = document.getElementById('turnstile-container');
const turnstileStatusEl = document.getElementById('turnstile-status');
const downloadBtn = document.getElementById('download');
const loadingIndicator = document.getElementById('loading');
const statusMessage = document.getElementById('status-message');
const downloadError = document.getElementById('download-error');
const resultsCard = document.querySelector('.results');
const topArtistsEl = document.getElementById('top-artists');
const topTracksEl = document.getElementById('top-tracks');
const listenTimeEl = document.getElementById('listen-time');
const topGenreEl = document.getElementById('top-genre');
const artistImg = document.getElementById('artist-img');
const artworkUploadInput = document.getElementById('artwork-upload');
const artworkUploadBtn = document.getElementById('artwork-upload-btn');
const artworkResetBtn = document.getElementById('artwork-reset-btn');
const artworkEditor = document.querySelector('.artwork-editor');
const artworkEditorControls = artworkEditor ? Array.from(artworkEditor.querySelectorAll('input[type="range"]')) : [];
const artworkScaleInput = document.getElementById('artwork-scale');
const artworkOffsetXInput = document.getElementById('artwork-offset-x');
const artworkOffsetYInput = document.getElementById('artwork-offset-y');
const artworkSourceInputs = document.querySelectorAll('input[name="artwork-source"]');
const artworkReleaseInput = Array.from(artworkSourceInputs).find((input) => input.value === 'release');
const artworkReleaseLabel = artworkReleaseInput ? artworkReleaseInput.closest('.artwork-source__option') : null;
const navidromeFields = document.getElementById('navidrome-fields');
const navidromeServerInput = document.getElementById('navidrome-server');
const navidromePasswordInput = document.getElementById('navidrome-password');
const wrappedCountEl = document.getElementById('wrapped-count');
const wrappedCountSinceEl = document.getElementById('wrapped-count-since');
let turnstileWidgetId = null;
const clientConfig = {
  turnstileEnabled: false,
  turnstileSiteKey: '',
};
let clientConfigPromise = null;
let turnstileRefreshPromise = null;
let turnstileRefreshResolve = null;
let turnstileRefreshReject = null;
let turnstileRefreshTimeout = null;

const canvasRenderer = createCanvasRenderer({ canvas, themeSelect, artistImg });

const SERVICE_USERNAME_COPY = {
  listenbrainz: {
    label: 'ListenBrainz username',
    placeholder: 'e.g. devmatei',
    emptyMessage: 'Enter a ListenBrainz username to get started.',
  },
  lastfm: {
    label: 'Last.fm username',
    placeholder: 'e.g. yourlastfmname',
    emptyMessage: 'Enter a Last.fm username to get started.',
  },
  navidrome: {
    label: 'Navidrome username',
    placeholder: 'e.g. alice',
    emptyMessage: 'Enter your Navidrome username to get started.',
  },
};

function getUsernameCopy(service) {
  return SERVICE_USERNAME_COPY[service] || {
    label: 'Music username',
    placeholder: 'e.g. devmatei',
    emptyMessage: 'Enter a username to get started.',
  };
}

function getSelectedService() {
  return serviceSelector.getValue();
}

function isNavidromeSelected() {
  return getSelectedService() === 'navidrome';
}

function clearNavidromeState() {
  if (state.coverObjectUrl && !state.customArtworkActive) {
    URL.revokeObjectURL(state.coverObjectUrl);
    state.coverObjectUrl = null;
  }
  state.navidromeClient = null;
  state.navidromeStats = null;
}

function handleServiceChange(nextValue) {
  const selectedService = nextValue || getSelectedService();
  const isNavidrome = selectedService === 'navidrome';
  const copy = getUsernameCopy(selectedService);
  const navCopy = getUsernameCopy('navidrome');
  if (usernameLabel) {
    usernameLabel.textContent = isNavidrome ? navCopy.label : copy.label;
    usernameLabel.setAttribute('for', isNavidrome && navidromeUsernameInput ? 'navidrome-username' : 'username');
  }
  if (usernameField) {
    usernameField.hidden = isNavidrome;
    if (typeof usernameField.required === 'boolean') {
      usernameField.required = !isNavidrome;
    }
    if (!isNavidrome) {
      usernameField.placeholder = copy.placeholder;
    }
  }
  if (navidromeUsernameInput) {
    navidromeUsernameInput.hidden = !isNavidrome;
    if (typeof navidromeUsernameInput.required === 'boolean') {
      navidromeUsernameInput.required = isNavidrome;
    } else if (isNavidrome) {
      navidromeUsernameInput.setAttribute('required', 'required');
    } else {
      navidromeUsernameInput.removeAttribute('required');
    }
    navidromeUsernameInput.placeholder = navCopy.placeholder;
  }
  if (navidromeFields) {
    navidromeFields.hidden = !isNavidrome;
    navidromeFields.style.display = isNavidrome ? '' : 'none';
    navidromeFields.setAttribute('aria-hidden', String(!isNavidrome));
  }
  if (turnstileWrapper) {
    turnstileWrapper.hidden = Boolean(isNavidrome || !isTurnstileEnabled());
  }
  disableReleaseArtworkOption(selectedService !== 'listenbrainz');
  if (!isNavidrome) {
    clearNavidromeState();
  }
}

function readNavidromeCredentials(username) {
  if (!navidromeServerInput || !navidromePasswordInput) {
    throw new Error('Navidrome inputs unavailable.');
  }
  const serverUrlRaw = navidromeServerInput.value.trim();
  const password = navidromePasswordInput.value;
  if (!serverUrlRaw) {
    throw new Error('Enter your Navidrome server URL (including http:// or https://).');
  }
  if (!/^https?:\/\//i.test(serverUrlRaw)) {
    throw new Error('Include http:// or https:// in the Navidrome server URL.');
  }
  if (!username) {
    throw new Error('Enter your Navidrome username to continue.');
  }
  if (!password) {
    throw new Error('Enter your Navidrome password or app token.');
  }
  const normalisedUrl = serverUrlRaw.replace(/\/+$/, '');
  return {
    serverUrl: normalisedUrl,
    password,
  };
}

function getServiceLabel(key) {
  if (SERVICE_LABELS[key]) {
    return SERVICE_LABELS[key];
  }
  return key ? `${key.charAt(0).toUpperCase()}${key.slice(1)}` : 'Make a Wrapped';
}

function isLikelyNetworkError(error) {
  if (!error) {
    return false;
  }
  if (error.__networkError) {
    return true;
  }
  const message = (error.message || '').toLowerCase();
  if (!message) {
    return false;
  }
  return message.includes('networkerror') || message.includes('network error') || message.includes('failed to fetch');
}

function recordSectionWarning(section, details) {
  state.sectionWarnings.push({ section, details });
}

function handleSectionNetworkFailure(section, fallbackMessage) {
  recordSectionWarning(section, fallbackMessage || 'Network error');
  switch (section) {
    case 'Top artists':
      topArtistsEl.textContent = 'Unable to load (network error).';
      break;
    case 'Top tracks':
      topTracksEl.textContent = 'Unable to load (network error).';
      break;
    case 'Minutes listened':
      listenTimeEl.textContent = '0';
      break;
    case 'Top genre':
      topGenreEl.textContent = 'No data (network error).';
      break;
    default:
      break;
  }
}
const state = {
  coverObjectUrl: null,
  generatedData: null,
  isCoverReady: false,
  customArtworkUrl: null,
  customArtworkActive: false,
  customArtworkPersistence: null,
  customArtworkServerToken: null,
  customArtworkServerExpiry: null,
  imageTransform: { scale: 1, offsetX: 0, offsetY: 0 },
  queueMessageVisible: false,
  artworkSource: 'artist',
  turnstileToken: null,
  turnstileTokenExpiry: null,
  navidromeClient: null,
  navidromeStats: null,
  sectionWarnings: [],
  imageWarningMessage: '',
};

const serviceSelector = createServiceSelector();
serviceSelector.init();
if (serviceHiddenInput) {
  serviceHiddenInput.addEventListener('servicechange', (event) => {
    const value = event && event.detail ? event.detail.value : null;
    handleServiceChange(value);
  });
}
handleServiceChange(serviceSelector.getValue());

function invalidateTurnstileToken() {
  if (!isTurnstileEnabled()) {
    return;
  }
  state.turnstileTokenExpiry = 0;
  writeSession(TURNSTILE_TOKEN_EXPIRY_KEY, '0');
}

function clearStoredTurnstileToken() {
  state.turnstileToken = null;
  state.turnstileTokenExpiry = null;
  removeSession(TURNSTILE_TOKEN_KEY);
  removeSession(TURNSTILE_TOKEN_EXPIRY_KEY);
  if (turnstileRefreshReject) {
    turnstileRefreshReject(new Error('Verification expired.'));
  }
  if (turnstileRefreshTimeout) {
    window.clearTimeout(turnstileRefreshTimeout);
    turnstileRefreshTimeout = null;
  }
  turnstileRefreshPromise = null;
  turnstileRefreshResolve = null;
  turnstileRefreshReject = null;
}

function persistTurnstileToken(token, ttlMs = TURNSTILE_TOKEN_TTL_MS) {
  if (!token) {
    clearStoredTurnstileToken();
    return;
  }
  const expiresAt = Date.now() + (Number(ttlMs) || TURNSTILE_TOKEN_TTL_MS);
  state.turnstileToken = token;
  state.turnstileTokenExpiry = expiresAt;
  writeSession(TURNSTILE_TOKEN_KEY, token);
  writeSession(TURNSTILE_TOKEN_EXPIRY_KEY, String(expiresAt));
  if (turnstileRefreshResolve) {
    turnstileRefreshResolve(token);
  }
  if (turnstileRefreshTimeout) {
    window.clearTimeout(turnstileRefreshTimeout);
    turnstileRefreshTimeout = null;
  }
  turnstileRefreshPromise = null;
  turnstileRefreshResolve = null;
  turnstileRefreshReject = null;
}

function restoreTurnstileTokenFromSession() {
  try {
    const storedToken = readSession(TURNSTILE_TOKEN_KEY);
    const storedExpiry = Number(readSession(TURNSTILE_TOKEN_EXPIRY_KEY));
    if (storedToken && Number.isFinite(storedExpiry) && Date.now() < storedExpiry) {
      state.turnstileToken = storedToken;
      state.turnstileTokenExpiry = storedExpiry;
      return true;
    }
    clearStoredTurnstileToken();
  } catch (error) {
    console.warn('Session storage unavailable; cannot restore Turnstile token.', error);
    state.turnstileToken = null;
    state.turnstileTokenExpiry = null;
  }
  return false;
}

function hasFreshTurnstileToken() {
  if (state.turnstileToken && (!state.turnstileTokenExpiry || Date.now() < state.turnstileTokenExpiry)) {
    return true;
  }
  return restoreTurnstileTokenFromSession();
}

async function refreshTurnstileToken() {
  if (!isTurnstileEnabled()) {
    return null;
  }
  if (turnstileRefreshPromise) {
    return turnstileRefreshPromise;
  }
  resetTurnstileToken();
  turnstileRefreshPromise = new Promise((resolve, reject) => {
    turnstileRefreshResolve = resolve;
    turnstileRefreshReject = reject;
    turnstileRefreshTimeout = window.setTimeout(() => {
      turnstileRefreshTimeout = null;
      turnstileRefreshPromise = null;
      turnstileRefreshResolve = null;
      turnstileRefreshReject = null;
      reject(new Error('Verification timed out. Please retry the challenge.'));
    }, 15000);
  });

  // If widget supports automatic execution, trigger it to avoid extra clicks.
  if (window.turnstile && typeof window.turnstile.execute === 'function' && turnstileWidgetId !== null) {
    try {
      window.turnstile.execute(turnstileWidgetId);
    } catch (error) {
      console.warn('Automatic Turnstile execution failed; waiting for user interaction.', error);
    }
  }

  return turnstileRefreshPromise;
}

function isTurnstileEnabled() {
  return Boolean(clientConfig.turnstileEnabled && clientConfig.turnstileSiteKey);
}

const storedArtworkSource = readLocal(ARTWORK_SOURCE_KEY);
if (storedArtworkSource === 'artist' || storedArtworkSource === 'release') {
  state.artworkSource = storedArtworkSource;
}
updateArtworkSourceControls(state.artworkSource);

artistImg.crossOrigin = 'anonymous';

canvasRenderer.preloadBackgrounds(() => drawCanvas());

form.addEventListener('submit', generateWrapped);
themeSelect.addEventListener('change', () => drawCanvas());

downloadBtn.addEventListener('click', () => {
  const link = document.createElement('a');
  link.download = 'listenbrainz-wrapped.png';
  link.href = canvas.toDataURL('image/png');
  link.click();
});

if (artworkUploadBtn && artworkUploadInput) {
  artworkUploadBtn.addEventListener('click', () => artworkUploadInput.click());
  artworkUploadInput.addEventListener('change', handleArtworkUpload);
}

if (artworkResetBtn) {
  artworkResetBtn.addEventListener('click', () => resetArtworkUpload());
}

if (artworkScaleInput) {
  artworkScaleInput.addEventListener('input', handleArtworkTransformChange);
}

if (artworkOffsetXInput) {
  artworkOffsetXInput.addEventListener('input', handleArtworkTransformChange);
}

if (artworkOffsetYInput) {
  artworkOffsetYInput.addEventListener('input', handleArtworkTransformChange);
}

artworkSourceInputs.forEach((input) => {
  input.addEventListener('change', () => {
    if (!input.checked) {
      return;
    }
    setArtworkSource(input.value);
  });
});

restoreImageTransform();
restoreStoredArtwork();
setArtworkEditorEnabled(state.customArtworkActive);
restoreTurnstileTokenFromSession();

window.addEventListener('load', () => {
  toggleDownload(false);
  const paint = () => window.requestAnimationFrame(drawCanvas);
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(paint).catch(paint);
  } else {
    paint();
  }
  refreshWrappedCount();
  window.setInterval(refreshWrappedCount, COUNTER_REFRESH_INTERVAL);
  if (state.customArtworkActive) {
    applyCustomArtwork();
  }
  ensureClientConfigLoaded()
    .then(() => {
      if (isTurnstileEnabled()) {
        initialiseTurnstile();
      } else if (turnstileWrapper) {
        turnstileWrapper.remove();
      }
    })
    .catch(() => {
      if (turnstileWrapper) {
        turnstileWrapper.remove();
      }
    });
});

function drawCanvas() {
  canvasRenderer.draw({
    data: state.generatedData,
    isCoverReady: state.isCoverReady,
    customArtworkActive: state.customArtworkActive,
    imageTransform: state.imageTransform,
  });
}

function toggleDownload(enabled) {
  downloadBtn.disabled = !enabled;
  downloadBtn.setAttribute('aria-disabled', String(!enabled));
}

function setLoading(isLoading) {
  loadingIndicator.hidden = !isLoading;
  downloadBtn.setAttribute('aria-busy', String(isLoading));
  if (isLoading) {
    serviceSelector.closeDropdown();
  }
  form.querySelectorAll('input, button, select').forEach((element) => {
    if (element !== themeSelect) {
      element.disabled = isLoading;
    }
  });
  if (artworkUploadBtn) {
    artworkUploadBtn.disabled = isLoading;
  }
  if (artworkResetBtn) {
    if (isLoading) {
      artworkResetBtn.disabled = true;
      artworkResetBtn.setAttribute('aria-disabled', 'true');
    } else if (state.customArtworkActive) {
      toggleArtworkReset(true);
    } else {
      toggleArtworkReset(false);
    }
  }
}

function setStatus(message, type = 'info') {
  if (!message) {
    statusMessage.hidden = true;
    statusMessage.textContent = '';
    return;
  }
  statusMessage.hidden = false;
  statusMessage.textContent = message;
  statusMessage.classList.toggle('error', type === 'error');
}

async function loadClientConfig() {
  try {
    const response = await fetch('/api/client-config', { cache: 'no-store' });
    if (!response.ok) {
      throw new Error(`Client config request failed (${response.status})`);
    }
    const payload = await response.json();
    clientConfig.turnstileEnabled = Boolean(payload.turnstileEnabled);
    clientConfig.turnstileSiteKey = payload.turnstileSiteKey || '';
    return true;
  } catch (error) {
    console.warn('Unable to load client config', error);
    clientConfig.turnstileEnabled = false;
    clientConfig.turnstileSiteKey = '';
    return false;
  }
}

async function ensureClientConfigLoaded() {
  if (!clientConfigPromise) {
    clientConfigPromise = loadClientConfig();
  }
  try {
    await clientConfigPromise;
  } catch (error) {
    console.warn('Client config unavailable, continuing with defaults.', error);
  }
}

function updateTurnstileStatus(message, tone = 'info') {
  if (!turnstileStatusEl) {
    return;
  }
  if (!message) {
    turnstileStatusEl.hidden = true;
    turnstileStatusEl.textContent = '';
    turnstileStatusEl.removeAttribute('data-tone');
    return;
  }
  turnstileStatusEl.hidden = false;
  turnstileStatusEl.textContent = message;
  turnstileStatusEl.setAttribute('data-tone', tone);
}

function waitForTurnstileApi(maxWait = 10000) {
  if (window.turnstile && typeof window.turnstile.render === 'function') {
    return Promise.resolve(window.turnstile);
  }
  return new Promise((resolve, reject) => {
    const start = Date.now();
    const poll = window.setInterval(() => {
      if (window.turnstile && typeof window.turnstile.render === 'function') {
        window.clearInterval(poll);
        resolve(window.turnstile);
        return;
      }
      if (Date.now() - start >= maxWait) {
        window.clearInterval(poll);
        reject(new Error('Turnstile script timed out.'));
      }
    }, 150);
  });
}

async function initialiseTurnstile() {
  if (!isTurnstileEnabled() || !turnstileWrapper || !turnstileContainer) {
    if (turnstileWrapper) {
      turnstileWrapper.remove();
    }
    return;
  }
  try {
    await waitForTurnstileApi();
    const alreadyValidated = hasFreshTurnstileToken();
    turnstileWrapper.hidden = false;
    updateTurnstileStatus(
      alreadyValidated
        ? 'Verification already completed for this session. You can generate your wrapped.'
        : 'Complete the verification to generate your wrapped.',
      alreadyValidated ? 'success' : 'info',
    );
    turnstileWidgetId = window.turnstile.render(turnstileContainer, {
      sitekey: clientConfig.turnstileSiteKey,
      action: 'generate_wrapped',
      callback(token) {
        persistTurnstileToken(token);
        updateTurnstileStatus('Verification completed for this session. Ready when you are.', 'success');
      },
      'expired-callback': () => {
        clearStoredTurnstileToken();
        updateTurnstileStatus('Verification expired. Please try again.', 'warning');
        if (turnstileRefreshReject) {
          turnstileRefreshReject(new Error('Verification expired.'));
        }
      },
      'error-callback': () => {
        clearStoredTurnstileToken();
        updateTurnstileStatus('Verification failed to load. Refresh to retry.', 'error');
        if (turnstileRefreshReject) {
          turnstileRefreshReject(new Error('Verification failed to load.'));
        }
      },
    });
  } catch (error) {
    console.error('Unable to initialise Turnstile', error);
    turnstileWrapper.hidden = false;
    updateTurnstileStatus('Verification service unavailable. Refresh and try again.', 'error');
  }
}

function ensureTurnstileTokenAvailable() {
  if (!isTurnstileEnabled()) {
    return true;
  }
  if (hasFreshTurnstileToken()) {
    updateTurnstileStatus('Verification already completed for this session. You can keep generating.', 'success');
    return true;
  }
  resetTurnstileToken();
  return false;
}

function resetTurnstileToken() {
  if (!isTurnstileEnabled()) {
    return;
  }
  clearStoredTurnstileToken();
  if (window.turnstile && typeof window.turnstile.reset === 'function' && turnstileWidgetId !== null) {
    window.turnstile.reset(turnstileWidgetId);
  }
  updateTurnstileStatus('Complete the verification to generate your wrapped.');
}

async function ensureTurnstileToken(forceRefresh = false) {
  if (!isTurnstileEnabled()) {
    return null;
  }
  if (!forceRefresh && hasFreshTurnstileToken()) {
    return state.turnstileToken;
  }
  return refreshTurnstileToken();
}

function applyTurnstileHeaders(options = {}) {
  if (!isTurnstileEnabled()) {
    return options;
  }
  if (!hasFreshTurnstileToken()) {
    throw new Error('Complete the verification challenge to continue.');
  }
  const mergedOptions = { ...options };
  const headers = new Headers(options.headers || {});
  headers.set('X-Turnstile-Token', state.turnstileToken);
  mergedOptions.headers = headers;
  return mergedOptions;
}

async function applyTurnstileHeadersAsync(options = {}, { forceRefreshToken = false } = {}) {
  if (!isTurnstileEnabled()) {
    return options;
  }
  await ensureTurnstileToken(forceRefreshToken);
  return applyTurnstileHeaders(options);
}

async function turnstileFetch(path, options = {}, { forceRefreshToken = false } = {}) {
  await ensureClientConfigLoaded();
  const mergedOptions = await applyTurnstileHeadersAsync(options, { forceRefreshToken });
  try {
    // Add timeout to fetch - be generous with timeouts for local/slow environments
    // Image endpoints can take longer due to external API calls.
    let timeoutMs = 60000;
    if (path.includes('/top/img/')) {
      timeoutMs = 120000;
    }
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
    
    try {
      const response = await fetch(serviceSelector.withService(path), {
        ...mergedOptions,
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      return response;
    } catch (error) {
      clearTimeout(timeoutId);
      if (error.name === 'AbortError') {
        const timeoutSeconds = Math.round(timeoutMs / 1000);
        throw new Error(`Request timeout (${timeoutSeconds}s)`);
      }
      throw error;
    }
  } finally {
    if (isTurnstileEnabled()) {
      invalidateTurnstileToken();
    }
  }
}

function handleTurnstileFailure(message, status) {
  if (!isTurnstileEnabled()) {
    return false;
  }
  const normalized = (message || '').toString().toLowerCase();
  const looksExpired = normalized.includes('verification expired') || normalized.includes('turnstile');
  if (status === 400 && looksExpired) {
    resetTurnstileToken();
    return true;
  }
  return false;
}

async function fetchWithTurnstileRetry(fetcher) {
  let retried = false;
  while (true) {
    try {
      return await fetcher();
    } catch (error) {
      const message = (error && error.message) || '';
      const expired = Boolean(error && (error.__turnstileExpired || message.toLowerCase().includes('verification')));
      if (!expired || retried || !isTurnstileEnabled()) {
        if (isLikelyNetworkError(error) || (error && error.name === 'TypeError')) {
          const baseMessage = 'Network error while contacting the selected service. Check your connection and try again.';
          const extra = error && error.message ? ` (${error.message})` : '';
          const netErr = new Error(`${baseMessage}${extra}`);
          netErr.__networkError = true;
          netErr.__networkErrorOriginal = error;
          throw netErr;
        }
        throw error;
      }
      retried = true;
      await refreshTurnstileToken();
    }
  }
}

function updateArtworkSourceControls(value) {
  artworkSourceInputs.forEach((input) => {
    input.checked = input.value === value;
  });
}

function setArtworkSource(value, { persist = true, refresh = true } = {}) {
  const next = value === 'release' ? 'release' : 'artist';
  const changed = state.artworkSource !== next;
  if (next === 'release' && isNavidromeSelected()) {
    return;
  }
  state.artworkSource = next;
  if (persist) {
    writeLocal(ARTWORK_SOURCE_KEY, next);
  }
  updateArtworkSourceControls(next);

  if (!refresh) {
    return;
  }
  if (state.customArtworkActive) {
    return;
  }
  if (!state.generatedData || !state.generatedData.username) {
    return;
  }
  if (!changed && state.isCoverReady) {
    return;
  }

  const username = state.generatedData.username;
  state.isCoverReady = false;
  toggleDownload(false);
  loadCoverArt(username)
    .then((ready) => {
      state.isCoverReady = ready;
      drawCanvas();
      downloadError.hidden = ready;
      toggleDownload(ready);
    })
    .catch((error) => {
      console.error('Unable to refresh artwork source', error);
      setStatus('Unable to refresh artwork for the selected source.', 'error');
      state.isCoverReady = false;
      downloadError.hidden = false;
      toggleDownload(false);
    });
}

function disableReleaseArtworkOption(disabled) {
  if (!artworkReleaseInput) {
    return;
  }
  artworkReleaseInput.disabled = Boolean(disabled);
  if (artworkReleaseLabel) {
    artworkReleaseLabel.setAttribute('aria-disabled', String(Boolean(disabled)));
    artworkReleaseLabel.classList.toggle('is-disabled', Boolean(disabled));
  }
  if (disabled && state.artworkSource !== 'artist') {
    setArtworkSource('artist', { persist: false, refresh: false });
  }
}

function handleArtworkTransformChange() {
  if (!state.customArtworkActive) {
    applyTransformToControls();
    return;
  }
  const nextScale = artworkScaleInput ? Number(artworkScaleInput.value) : state.imageTransform.scale;
  const nextOffsetX = artworkOffsetXInput ? Number(artworkOffsetXInput.value) : state.imageTransform.offsetX;
  const nextOffsetY = artworkOffsetYInput ? Number(artworkOffsetYInput.value) : state.imageTransform.offsetY;
  state.imageTransform = {
    scale: Number.isFinite(nextScale) ? nextScale : 1,
    offsetX: Number.isFinite(nextOffsetX) ? nextOffsetX : 0,
    offsetY: Number.isFinite(nextOffsetY) ? nextOffsetY : 0,
  };
  saveImageTransform();
  drawCanvas();
}

function applyTransformToControls() {
  if (artworkScaleInput) {
    artworkScaleInput.value = String(state.imageTransform.scale);
  }
  if (artworkOffsetXInput) {
    artworkOffsetXInput.value = String(state.imageTransform.offsetX);
  }
  if (artworkOffsetYInput) {
    artworkOffsetYInput.value = String(state.imageTransform.offsetY);
  }
}

function saveImageTransform() {
  if (!state.customArtworkActive) {
    return;
  }
  writeLocal(ARTWORK_TRANSFORM_KEY, JSON.stringify(state.imageTransform));
}

function toggleArtworkReset(enabled) {
  if (!artworkResetBtn) {
    return;
  }
  artworkResetBtn.disabled = !enabled;
  artworkResetBtn.setAttribute('aria-disabled', String(!enabled));
}

function setArtworkEditorEnabled(enabled) {
  if (artworkEditor) {
    artworkEditor.setAttribute('aria-disabled', String(!enabled));
  }
  artworkEditorControls.forEach((input) => {
    input.disabled = !enabled;
  });
}

async function applyCustomArtwork() {
  if (!state.customArtworkActive || !state.customArtworkUrl) {
    return false;
  }
  const loaded = await loadImage(artistImg, state.customArtworkUrl);
  if (loaded) {
    state.isCoverReady = true;
    downloadError.hidden = true;
    toggleDownload(true);
    setArtworkEditorEnabled(true);
    drawCanvas();
    return true;
  }
  setStatus(state.customArtworkPersistence === 'server'
    ? 'Server-stored artwork expired. Please upload a new image.'
    : 'Could not load that image. Try a different file.', 'error');
  resetArtworkUpload({ silent: true });
  return false;
}

async function handleArtworkUpload(event) {
  const file = event.target.files && event.target.files[0];
  if (!file) {
    return;
  }
  if (!file.type.startsWith('image/')) {
    setStatus('Please select a valid image file.', 'error');
    event.target.value = '';
    return;
  }
  if (file.size > MAX_ARTWORK_BYTES) {
    setStatus('Image must be smaller than 6 MB.', 'error');
    event.target.value = '';
    return;
  }
  try {
    const dataUrl = await readFileAsDataUrl(file);
    const stored = writeLocal(ARTWORK_STORAGE_KEY, dataUrl);
    if (!stored) {
      removeLocal(ARTWORK_STORAGE_KEY);
      await uploadArtworkToServer(file);
      return;
    }
    clearServerToken();
    state.customArtworkUrl = dataUrl;
    state.customArtworkActive = true;
    state.customArtworkPersistence = 'local';
    toggleArtworkReset(true);
    setArtworkEditorEnabled(true);
    setStatus('Custom artwork saved to your browser.');
    await applyCustomArtwork();
  } catch (error) {
    console.warn('Local artwork save failed, falling back to server.', error);
    try {
      await uploadArtworkToServer(file);
    } catch (uploadError) {
      console.error(uploadError);
      setStatus('Something went wrong while loading the artwork.', 'error');
      resetArtworkUpload({ silent: true });
    }
  }
}

function resetArtworkUpload(options = {}) {
  const { silent = false } = options;
  if (state.customArtworkUrl && state.customArtworkUrl.startsWith('blob:')) {
    URL.revokeObjectURL(state.customArtworkUrl);
  }
  state.customArtworkUrl = null;
  state.customArtworkActive = false;
  state.customArtworkPersistence = null;
  removeLocal(ARTWORK_STORAGE_KEY);
  clearServerToken();
  if (artworkUploadInput) {
    artworkUploadInput.value = '';
  }
  toggleArtworkReset(false);
  setArtworkEditorEnabled(false);
  if (!silent) {
    setStatus('Custom artwork cleared. The next generation will fetch artwork automatically again.');
  }
  if (state.generatedData && state.generatedData.username) {
    loadCoverArt(state.generatedData.username).then((success) => {
      state.isCoverReady = success;
      downloadError.hidden = success;
      toggleDownload(success);
      drawCanvas();
    });
  } else {
    state.isCoverReady = false;
    toggleDownload(false);
  }
}

function restoreImageTransform() {
  const raw = readLocal(ARTWORK_TRANSFORM_KEY);
  if (!raw) {
    applyTransformToControls();
    return;
  }
  try {
    const parsed = JSON.parse(raw);
    state.imageTransform = {
      scale: Number.isFinite(parsed.scale) ? parsed.scale : 1,
      offsetX: Number.isFinite(parsed.offsetX) ? parsed.offsetX : 0,
      offsetY: Number.isFinite(parsed.offsetY) ? parsed.offsetY : 0,
    };
  } catch (error) {
    console.warn('Failed to parse stored artwork transform.', error);
    state.imageTransform = { scale: 1, offsetX: 0, offsetY: 0 };
  }
  applyTransformToControls();
}

function restoreStoredArtwork() {
  const storedData = readLocal(ARTWORK_STORAGE_KEY);
  if (storedData) {
    state.customArtworkUrl = storedData;
    state.customArtworkActive = true;
    state.customArtworkPersistence = 'local';
    toggleArtworkReset(true);
    setArtworkEditorEnabled(true);
    applyCustomArtwork();
    return;
  }
  try {
    const token = readSession(ARTWORK_TOKEN_KEY);
    const expiry = Number(readSession(ARTWORK_TOKEN_EXPIRY_KEY));
    if (token && Number.isFinite(expiry) && Date.now() < expiry) {
      state.customArtworkServerToken = token;
      state.customArtworkServerExpiry = expiry;
      state.customArtworkUrl = `/artwork/${token}`;
      state.customArtworkActive = true;
      state.customArtworkPersistence = 'server';
      toggleArtworkReset(true);
      setArtworkEditorEnabled(true);
      applyCustomArtwork();
    }
  } catch (error) {
    console.warn('Session storage unavailable; cannot restore server artwork token.', error);
  }
}

function persistServerToken(token, expiresInSeconds) {
  state.customArtworkServerToken = token;
  state.customArtworkServerExpiry = Date.now() + (Number(expiresInSeconds) || 0) * 1000;
  writeSession(ARTWORK_TOKEN_KEY, state.customArtworkServerToken);
  writeSession(ARTWORK_TOKEN_EXPIRY_KEY, String(state.customArtworkServerExpiry));
}

function clearServerToken() {
  state.customArtworkServerToken = null;
  state.customArtworkServerExpiry = null;
  removeSession(ARTWORK_TOKEN_KEY);
  removeSession(ARTWORK_TOKEN_EXPIRY_KEY);
}

function updateWrappedCounter(count, since) {
  if (!wrappedCountEl) {
    return;
  }
  const parsed = Number(count);
  if (!Number.isFinite(parsed)) {
    return;
  }
  wrappedCountEl.textContent = parsed.toLocaleString();
  if (wrappedCountSinceEl && since) {
    let formatted = since;
    const parsedDate = new Date(since);
    if (!Number.isNaN(parsedDate.getTime())) {
      formatted = parsedDate.toLocaleString(undefined, { month: 'short', year: 'numeric' });
    }
    wrappedCountSinceEl.textContent = formatted;
  }
}

async function refreshWrappedCount() {
  if (!wrappedCountEl) {
    return;
  }
  try {
    const response = await fetch('/metrics/wrapped', { cache: 'no-store' });
    if (!response.ok) {
      return;
    }
    const data = await response.json();
    updateWrappedCounter(data.count, data.since);
  } catch (error) {
    console.warn('Unable to refresh wrapped counter', error);
  }
}

async function recordWrappedGenerated() {
  try {
    const response = await fetch('/metrics/wrapped', { method: 'POST' });
    if (!response.ok) {
      throw new Error(await parseError(response));
    }
    const data = await response.json();
    updateWrappedCounter(data.count, data.since);
  } catch (error) {
    console.error('Unable to record wrapped generation', error);
  }
}

async function generateWrapped(event) {
  event.preventDefault();
  await ensureClientConfigLoaded();
  const selectedService = getSelectedService();
  const usernameInput = selectedService === 'navidrome' ? navidromeUsernameInput : usernameField;
  const username = usernameInput ? usernameInput.value.trim() : '';
  if (!username) {
    const copy = getUsernameCopy(selectedService);
    setStatus(copy.emptyMessage || 'Enter a username to get started.', 'error');
    return;
  }

  let navidromeCredentials = null;
  if (selectedService === 'navidrome') {
    try {
      navidromeCredentials = readNavidromeCredentials(username);
    } catch (credentialError) {
      setStatus(credentialError.message, 'error');
      return;
    }
    state.navidromeClient = new NavidromeClient(
      navidromeCredentials.serverUrl,
      username,
      navidromeCredentials.password,
    );
    setStatus('Navidrome: scanning your library locally. This can take a minute for big collections.');
  }

  const hasExisting = Boolean(state.generatedData);
  const sameProfile = hasExisting
    && state.generatedData.username === username
    && state.generatedData.service === selectedService;
  let sectionsToRefresh = [...ALL_SECTIONS];

  if (hasExisting) {
    const existingLabel = `"${state.generatedData.username}" via ${getServiceLabel(state.generatedData.service || 'listenbrainz')}`;
    const promptMessage = [
      sameProfile
        ? 'You already generated a wrapped for this selection.'
        : `Current wrapped belongs to ${existingLabel}.`,
      'Type:',
      '- keep — keep the existing poster',
      '- new — refresh everything',
      '- or list sections to refresh (artists, tracks, time, genre, image)',
    ].join('\n');
    const choiceRaw = window.prompt(promptMessage, 'new');
    if (choiceRaw === null) {
      setStatus('Generation cancelled.');
      return;
    }
    const choice = choiceRaw.trim().toLowerCase();
    if (choice === 'keep' || choice === 'old' || choice === 'current') {
      resultsCard.hidden = false;
      drawCanvas();
      downloadError.hidden = state.isCoverReady;
      toggleDownload(state.isCoverReady);
      setStatus('Keeping your current wrapped.');
      return;
    }
    if (choice && choice !== 'new') {
      const parsed = parseSectionSelection(choice);
      if (!parsed.length) {
        setStatus('No valid sections selected; keeping current wrapped.');
        toggleDownload(state.isCoverReady);
        return;
      }
      sectionsToRefresh = parsed;
    }
  }

  if (!hasExisting || !sameProfile) {
    sectionsToRefresh = [...ALL_SECTIONS];
  }

  if (selectedService === 'navidrome' && sectionsToRefresh.some((section) => section !== 'image')) {
    state.navidromeStats = null;
  }

  if (selectedService !== 'navidrome' && !ensureTurnstileTokenAvailable()) {
    setStatus('Complete the verification challenge before generating.', 'error');
    return;
  }

  const refreshImage = sectionsToRefresh.includes('image');

  setStatus('');
  setLoading(true);
  if (!hasExisting || sectionsToRefresh.length === ALL_SECTIONS.length) {
    resultsCard.hidden = true;
  }
  if (refreshImage) {
    downloadError.hidden = true;
    if (state.customArtworkActive && state.customArtworkUrl) {
      state.isCoverReady = true;
      toggleDownload(true);
    } else {
      toggleDownload(false);
      state.isCoverReady = false;
    }
  }

  try {
    if (!state.generatedData) {
      state.generatedData = {};
    }
    state.generatedData.username = username;
    state.generatedData.service = selectedService;

    state.sectionWarnings = [];
    await updateSections(username, sectionsToRefresh);

    drawCanvas();
    resultsCard.hidden = false;
    if (sectionsToRefresh.length === ALL_SECTIONS.length) {
      await recordWrappedGenerated();
    }
    const baseLabel = sectionsToRefresh.length === ALL_SECTIONS.length
      ? `Wrapped refreshed for ${username}.`
      : `Updated ${formatSectionListForStatus(sectionsToRefresh)}.`;
    if (state.sectionWarnings.length) {
      const affected = state.sectionWarnings.map((entry) => entry.section).join(', ');
      setStatus(`${baseLabel} Some sections could not load (${affected}).`, 'error');
    } else {
      setStatus(baseLabel);
    }
  } catch (error) {
    console.error(error);
    setStatus(error.message || 'Something went wrong. Try again in a moment.', 'error');
  } finally {
    downloadError.hidden = state.isCoverReady;
    toggleDownload(state.isCoverReady);
    setLoading(false);
  }
}

async function fetchJson(path) {
  const fetcher = async () => {
    const response = await turnstileFetch(path, { cache: 'no-store' });
    if (!response.ok) {
      const errorMessage = await parseError(response);
      if (handleTurnstileFailure(errorMessage, response.status)) {
        const err = new Error('Verification expired. Please complete the challenge again.');
        err.__turnstileExpired = true;
        throw err;
      }
      throw new Error(errorMessage);
    }
    return response.json();
  };
  return fetchWithTurnstileRetry(fetcher);
}

async function fetchText(path) {
  const fetcher = async () => {
    const response = await turnstileFetch(path, { cache: 'no-store' });
    if (!response.ok) {
      const errorMessage = await parseError(response);
      if (handleTurnstileFailure(errorMessage, response.status)) {
        const err = new Error('Verification expired. Please complete the challenge again.');
        err.__turnstileExpired = true;
        throw err;
      }
      throw new Error(errorMessage);
    }
    return response.text();
  };
  return fetchWithTurnstileRetry(fetcher);
}

async function parseError(response) {
  const fallback = `Request failed (${response.status})`;
  const contentType = response.headers.get('content-type') || '';
  try {
    if (contentType.includes('application/json')) {
      const body = await response.json();
      return body.description || body.error || fallback;
    }
    const text = await response.text();
    if (!text) {
      return fallback;
    }
    return text.replace(/<[^>]+>/g, '').trim() || fallback;
  } catch (error) {
    console.error(error);
    return fallback;
  }
}

async function uploadArtworkToServer(file) {
  await ensureClientConfigLoaded();
  removeLocal(ARTWORK_STORAGE_KEY);
  const formData = new FormData();
  formData.append('artwork', file, file.name || 'artwork.png');
  const response = await fetchWithTurnstileRetry(async () => {
    const res = await turnstileFetch('/artwork/upload', {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const errorMessage = await parseError(res);
      if (handleTurnstileFailure(errorMessage, res.status)) {
        const err = new Error('Verification expired. Please complete the challenge again.');
        err.__turnstileExpired = true;
        throw err;
      }
      const err = new Error(errorMessage);
      err.__turnstileExpired = false;
      throw err;
    }
    return res;
  });
  const payload = await response.json();
  state.customArtworkUrl = `/artwork/${payload.token}`;
  state.customArtworkActive = true;
  state.customArtworkPersistence = 'server';
  persistServerToken(payload.token, payload.expires_in || 0);
  toggleArtworkReset(true);
  setArtworkEditorEnabled(true);
  setStatus('Artwork stored server-side for up to 1 hour, then purged automatically.');
  await applyCustomArtwork();
}

async function loadCoverArt(username) {
  if (isNavidromeSelected()) {
    if (state.customArtworkActive && state.customArtworkUrl) {
      return applyCustomArtwork();
    }
    return loadNavidromeCoverArt();
  }
  await ensureClientConfigLoaded();
  if (state.customArtworkActive && state.customArtworkUrl) {
    if (state.coverObjectUrl) {
      URL.revokeObjectURL(state.coverObjectUrl);
      state.coverObjectUrl = null;
    }
    return applyCustomArtwork();
  }
  setArtworkEditorEnabled(false);
  if (state.coverObjectUrl) {
    URL.revokeObjectURL(state.coverObjectUrl);
    state.coverObjectUrl = null;
  }

  state.imageWarningMessage = '';
  const requestArtistImage = async (source) => {
    const imageParams = new URLSearchParams();
    if (source === 'release') {
      imageParams.set('source', 'release');
    }
    const imagePath = `/top/img/${encodeURIComponent(username)}${imageParams.toString() ? `?${imageParams.toString()}` : ''}`;
    const { response, blob } = await fetchWithTurnstileRetry(async () => {
      const res = await turnstileFetch(imagePath, { cache: 'no-store' });
      if (res.status === 429) {
        const err429 = new Error(await parseError(res));
        err429.__turnstileExpired = false;
        throw err429;
      }
      if (!res.ok) {
        const errorMessage = await parseError(res);
        if (handleTurnstileFailure(errorMessage, res.status)) {
          const errTurn = new Error('Verification expired. Please complete the challenge again.');
          errTurn.__turnstileExpired = true;
          throw errTurn;
        }
        const unavailable = new Error(errorMessage || 'Artist image unavailable');
        unavailable.__turnstileExpired = false;
        throw unavailable;
      }
      const blobResult = await res.blob();
      return { response: res, blob: blobResult };
    });
    return { response, blob, source };
  };

  const preferredSources = state.artworkSource === 'release' ? ['release', 'artist'] : ['artist', 'release'];
  const triedSources = new Set();
  const failedSources = [];

  for (const sourceOption of preferredSources) {
    if (triedSources.has(sourceOption)) {
      continue;
    }
    triedSources.add(sourceOption);
    const maxAttempts = 2;
    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      try {
        const { response, blob } = await requestArtistImage(sourceOption);
        const queuePosition = Number(response.headers.get('X-Image-Queue-Position'));
        if (Number.isFinite(queuePosition) && queuePosition > 0) {
          setStatus(`Image queue is busy (position ${queuePosition}). Hang tight, we’ll grab the art asap.`);
          state.queueMessageVisible = true;
        } else if (state.queueMessageVisible) {
          setStatus('');
          state.queueMessageVisible = false;
        }
        state.coverObjectUrl = URL.createObjectURL(blob);
        const loaded = await loadImage(artistImg, state.coverObjectUrl);
        if (!loaded) {
          throw new Error('Artist image failed to load');
        }
        if (sourceOption !== state.artworkSource) {
          console.info(`Artist image loaded via ${sourceOption} fallback.`);
        }
        state.imageWarningMessage = '';
        return true;
      } catch (error) {
        const networkIssue = isLikelyNetworkError(error);
        const timeoutIssue = (error?.message || '').toLowerCase().includes('timeout');
        const shouldRetry = attempt < maxAttempts && (networkIssue || timeoutIssue);
        if (!shouldRetry) {
          failedSources.push(`${sourceOption}: ${error?.message || 'unavailable'}`);
          break;
        }
        // brief delay before retrying the same source
        await new Promise((resolve) => setTimeout(resolve, 700));
      }
    }
  }

  if (state.queueMessageVisible) {
    setStatus('');
    state.queueMessageVisible = false;
  }
  if (failedSources.length) {
    state.imageWarningMessage = failedSources.join(' | ');
  } else {
    state.imageWarningMessage = 'Artist image unavailable';
  }
  await loadImage(artistImg, BACKGROUND_SOURCES.black);
  return false;
}

async function loadNavidromeCoverArt() {
  if (!state.navidromeClient || !state.navidromeStats) {
    await loadImage(artistImg, BACKGROUND_SOURCES.black);
    return false;
  }
  setArtworkEditorEnabled(false);
  if (state.coverObjectUrl) {
    URL.revokeObjectURL(state.coverObjectUrl);
    state.coverObjectUrl = null;
  }
  const topAlbums = Array.isArray(state.navidromeStats.topAlbumsByPlaycount)
    ? state.navidromeStats.topAlbumsByPlaycount
    : [];
  const topSongs = Array.isArray(state.navidromeStats.topSongsByPlaycount)
    ? state.navidromeStats.topSongsByPlaycount
    : [];
  const coverSource = topAlbums[0] || topSongs[0] || {};
  const coverId = coverSource.coverArtId || coverSource.id || coverSource.albumId;
  if (!coverId) {
    await loadImage(artistImg, BACKGROUND_SOURCES.black);
    return false;
  }
  try {
    const blob = await state.navidromeClient.fetchCoverArt(coverId);
    if (!blob) {
      throw new Error('Empty cover art response');
    }
    state.coverObjectUrl = URL.createObjectURL(blob);
    const loaded = await loadImage(artistImg, state.coverObjectUrl);
    if (!loaded) {
      throw new Error('Cover art failed to load');
    }
    return true;
  } catch (error) {
    console.error('Unable to load Navidrome cover art', error);
    await loadImage(artistImg, BACKGROUND_SOURCES.black);
    return false;
  }
}

async function updateSections(username, sections) {
  if (isNavidromeSelected()) {
    await updateNavidromeSections(sections);
    refreshSectionDisplays();
    return;
  }
  await updateListenBrainzSections(username, sections);
  refreshSectionDisplays();
}

async function updateListenBrainzSections(username, sections) {
  const queue = [];

  if (sections.includes('artists')) {
    queue.push({
      section: 'Top artists',
      run: async () => {
        const artists = sanitiseRankedArray(await fetchJson(`/top/artists/${encodeURIComponent(username)}/5`));
        state.generatedData.artists = artists;
        topArtistsEl.textContent = formatRankedList(artists);
      },
    });
  }

  if (sections.includes('tracks')) {
    queue.push({
      section: 'Top tracks',
      run: async () => {
        const tracks = sanitiseRankedArray(await fetchJson(`/top/tracks/${encodeURIComponent(username)}/5`));
        state.generatedData.tracks = tracks;
        topTracksEl.textContent = formatRankedList(tracks);
      },
    });
  }

  if (sections.includes('time')) {
    queue.push({
      section: 'Minutes listened',
      run: async () => {
        const minutes = ensureMinutesLabel(await fetchText(`/time/total/${encodeURIComponent(username)}`));
        state.generatedData.minutes = minutes;
        listenTimeEl.textContent = minutes;
      },
    });
  }

  if (sections.includes('genre')) {
    queue.push({
      section: 'Top genre',
      run: async () => {
        const genre = await fetchText(`/top/genre/user/${encodeURIComponent(username)}`);
        const normalised = normaliseGenreLabel(genre);
        state.generatedData.genre = normalised;
        topGenreEl.textContent = normalised;
      },
    });
  }

  if (sections.includes('image')) {
    queue.push({
      section: 'Artist image',
      run: async () => {
        if (state.customArtworkActive && state.customArtworkUrl) {
          state.isCoverReady = await applyCustomArtwork();
        } else {
          state.isCoverReady = await loadCoverArt(username);
        }
        if (!state.isCoverReady) {
          recordSectionWarning('Artist image', state.imageWarningMessage || 'Fallback background used');
        }
      },
    });
  }

  // Run sequentially to avoid reusing a single Turnstile token across parallel requests.
  /* eslint-disable no-await-in-loop */
  for (const task of queue) {
    try {
      await task.run();
    } catch (error) {
      if (isLikelyNetworkError(error)) {
        console.warn(`Network error loading ${task.section}`, error);
        handleSectionNetworkFailure(task.section, error.message);
        continue;
      }
      throw error;
    }
  }
  /* eslint-enable no-await-in-loop */

  if (!sections.includes('artists') && Array.isArray(state.generatedData.artists)) {
    topArtistsEl.textContent = formatRankedList(state.generatedData.artists);
  }
  if (!sections.includes('tracks') && Array.isArray(state.generatedData.tracks)) {
    topTracksEl.textContent = formatRankedList(state.generatedData.tracks);
  }
  if (!sections.includes('time') && typeof state.generatedData.minutes === 'string') {
    listenTimeEl.textContent = ensureMinutesLabel(state.generatedData.minutes);
  }
  if (!sections.includes('genre') && typeof state.generatedData.genre === 'string') {
    topGenreEl.textContent = normaliseGenreLabel(state.generatedData.genre);
  }
}

async function updateNavidromeSections(sections) {
  if (!state.navidromeClient) {
    throw new Error('Navidrome connection unavailable. Enter your server details again.');
  }
  const needsStats = !state.navidromeStats || sections.some((section) => section !== 'image');
  if (needsStats) {
    state.navidromeStats = await state.navidromeClient.stats((percent, message, step) => {
      const pct = Number.isFinite(percent) ? `${Math.round(percent)}%` : '';
      const prefix = step ? `${step}: ` : '';
      setStatus(`Navidrome: ${prefix}${message} ${pct}`.trim());
    });
  }
  const stats = state.navidromeStats;
  if (!stats) {
    throw new Error('Navidrome stats unavailable.');
  }
  if (sections.includes('artists') || !Array.isArray(state.generatedData.artists)) {
    state.generatedData.artists = (stats.topArtistsByPlays || [])
      .slice(0, 5)
      .map((entry) => (Array.isArray(entry) ? entry[0] : entry) || 'Unknown artist');
  }
  if (sections.includes('tracks') || !Array.isArray(state.generatedData.tracks)) {
    state.generatedData.tracks = (stats.topSongsByPlaycount || [])
      .slice(0, 5)
      .map((song) => song.title || 'Unknown track');
  }
  if (sections.includes('time') || typeof state.generatedData.minutes !== 'string') {
    const totalMinutes = Math.max(0, Math.round((stats.listeningTime || 0) / 60));
    state.generatedData.minutes = totalMinutes.toLocaleString();
  }
  if (sections.includes('genre') || typeof state.generatedData.genre !== 'string') {
    const topGenreEntry = Array.isArray(stats.albumBasedStats?.topGenresByPlays)
      ? stats.albumBasedStats.topGenresByPlays[0]
      : null;
    state.generatedData.genre = (topGenreEntry && topGenreEntry[0]) || 'No genre';
  }
  if (sections.includes('image')) {
    if (state.customArtworkActive && state.customArtworkUrl) {
      state.isCoverReady = await applyCustomArtwork();
    } else {
      state.isCoverReady = await loadNavidromeCoverArt();
    }
  }
}

function refreshSectionDisplays() {
  if (Array.isArray(state.generatedData.artists)) {
    topArtistsEl.textContent = formatRankedList(state.generatedData.artists);
  }
  if (Array.isArray(state.generatedData.tracks)) {
    topTracksEl.textContent = formatRankedList(state.generatedData.tracks);
  }
  if (typeof state.generatedData.minutes === 'string') {
    listenTimeEl.textContent = ensureMinutesLabel(state.generatedData.minutes);
  }
  if (typeof state.generatedData.genre === 'string') {
    topGenreEl.textContent = normaliseGenreLabel(state.generatedData.genre);
  }
}

console.log('%c👋 Howdy developer! \n\n%cThis is an open-source project by DevMatei\n\n%cGitHub:%chttps://github.com/devmatei/listenbrainz-wrapped',
  'font-size: 16px; font-weight: bold; color: #6366f1;',
  'font-size: 14px; color: #4b5563;',
  'font-size: 15px; color: #4b5563;',
  'font-size: 15px; color: #2563eb; text-decoration: underline;'
)
