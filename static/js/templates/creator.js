import { readLocal, writeLocal } from '../storage.js';

const SECRET_KEY = 'wrappedCreatorSecret';
const NAME_KEY = 'wrappedCreatorName';
const WEBSITE_KEY = 'wrappedCreatorWebsite';
const BIO_KEY = 'wrappedCreatorBio';

function randomSecret() {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return Array.from(bytes)
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');
}

async function sha256Hex(value) {
  const buffer = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value));
  return Array.from(new Uint8Array(buffer))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');
}

export async function ensureCreatorSecret() {
  let secret = readLocal(SECRET_KEY);
  if (!secret || !/^[A-Za-z0-9_-]{16,64}$/.test(secret)) {
    secret = randomSecret();
    writeLocal(SECRET_KEY, secret);
  }
  return secret;
}

export async function getCreatorId() {
  const secret = await ensureCreatorSecret();
  const hash = await sha256Hex(secret);
  return `c${hash.slice(0, 12)}`;
}

export function getCreatorDisplay() {
  return {
    name: readLocal(NAME_KEY) || '',
    website: readLocal(WEBSITE_KEY) || '',
    bio: readLocal(BIO_KEY) || '',
  };
}

export function setCreatorDisplay({ name, website, bio }) {
  if (name) {
    writeLocal(NAME_KEY, name);
  }
  if (website) {
    writeLocal(WEBSITE_KEY, website);
  }
  if (bio) {
    writeLocal(BIO_KEY, bio);
  }
}

export async function buildCreatorPayload() {
  const secret = await ensureCreatorSecret();
  const id = await getCreatorId();
  const display = getCreatorDisplay();
  return {
    id,
    secret,
    name: display.name || id.slice(0, 8),
    website: display.website,
    bio: display.bio,
  };
}
