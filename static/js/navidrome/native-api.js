import { normaliseServerUrl } from './helpers.js';
import { NAVIDROME_SCRABBLE_PAGE_SIZE } from './constants.js';

export class NavidromeNativeApi {
  constructor(serverUrl, username, password) {
    this.root = normaliseServerUrl(serverUrl);
    this.user = username;
    this.password = password;
    this.token = null;
  }

  async authenticate() {
    if (this.token) {
      return this.token;
    }
    let response;
    try {
      response = await fetch(`${this.root}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ username: this.user, password: this.password }),
      });
    } catch (error) {
      throw new Error('Unable to reach your Navidrome server. Check the URL and network settings.');
    }
    if (!response.ok) {
      throw new Error('Navidrome authentication failed. Check the username and password.');
    }
    let payload;
    try {
      payload = await response.json();
    } catch (error) {
      throw new Error('Navidrome login returned an invalid response.');
    }
    if (!payload || typeof payload.token !== 'string' || !payload.token) {
      throw new Error('Navidrome login returned no token.');
    }
    this.token = payload.token;
    return this.token;
  }

  async requestJson(path, params = null) {
    await this.authenticate();
    const query = params ? `?${params.toString()}` : '';
    let response;
    try {
      response = await fetch(`${this.root}${path}${query}`, {
        method: 'GET',
        headers: { Accept: 'application/json', 'x-nd-authorization': `Bearer ${this.token}` },
      });
    } catch (error) {
      throw new Error('Unable to reach your Navidrome server. Check the URL and network settings.');
    }
    if (!response.ok) {
      if (response.status === 404 && path.startsWith('/api/scrobble')) {
        throw new Error('Your Navidrome does not expose the scrobble Native API yet. Upgrade to a build that ships /api/scrobble, or switch the stats method back to Legacy.');
      }
      throw new Error(`Navidrome Native API request failed (${response.status} - ${response.statusText})`);
    }
    try {
      return await response.json();
    } catch (error) {
      throw new Error('Navidrome Native API returned an invalid response.');
    }
  }

  async fetchScrobbles(fromTs, toTs) {
    const scrobbles = [];
    let offset = 0;
    for (;;) {
      const params = new URLSearchParams({
        from: String(fromTs),
        to: String(toTs),
        _sort: 'submission_time',
        _order: 'asc',
        _start: String(offset),
        _end: String(offset + NAVIDROME_SCRABBLE_PAGE_SIZE),
      });
      const rows = await this.requestJson('/api/scrobble', params);
      const page = Array.isArray(rows) ? rows : [];
      scrobbles.push(...page);
      if (page.length < NAVIDROME_SCRABBLE_PAGE_SIZE) {
        break;
      }
      offset += NAVIDROME_SCRABBLE_PAGE_SIZE;
    }
    return scrobbles;
  }

  async fetchSong(id) {
    const data = await this.requestJson(`/api/song/${encodeURIComponent(id)}`);
    return data && typeof data === 'object' ? data : null;
  }
}
