export function normaliseServerUrl(url) {
  if (!url) {
    return '';
  }
  return url.replace(/\/+$/, '');
}

export function buildRandomSalt(length = 16) {
  if (typeof crypto !== 'undefined' && crypto.getRandomValues) {
    const array = new Uint8Array(length);
    crypto.getRandomValues(array);
    return Array.from(array, (byte) => byte.toString(16).padStart(2, '0'))
      .join('')
      .slice(0, length);
  }
  return Array.from({ length }, () => Math.floor(Math.random() * 16).toString(16)).join('');
}
