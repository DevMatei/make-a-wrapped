import { md5 } from '../md5.js';
import { NAVIDROME_API_VERSION, NAVIDROME_CLIENT_ID } from './constants.js';
import { buildRandomSalt, normaliseServerUrl } from './helpers.js';

export class NavidromeApi {
  constructor(serverUrl, username, password) {
    this.root = normaliseServerUrl(serverUrl);
    this.user = username;
    this.password = password;
    this.base = `${this.root}/rest`;
  }

  buildParams(params = {}, { json = true } = {}) {
    const salt = buildRandomSalt();
    const token = md5(`${this.password}${salt}`);
    const search = new URLSearchParams({
      u: this.user,
      t: token,
      s: salt,
      v: NAVIDROME_API_VERSION,
      c: NAVIDROME_CLIENT_ID,
      ...(json ? { f: 'json' } : {}),
      ...params,
    });
    return search;
  }

  async requestJson(endpoint, params = {}) {
    const query = this.buildParams(params, { json: true });
    let response;
    try {
      response = await fetch(`${this.base}/${endpoint}?${query.toString()}`, {
        method: 'GET',
        headers: { Accept: 'application/json' },
      });
    } catch (error) {
      throw new Error('Unable to reach your Navidrome server. Check the URL and network settings.');
    }
    if (!response.ok) {
      throw new Error(`Navidrome request failed (${response.status} - ${response.statusText})`);
    }
    let data;
    try {
      data = await response.json();
    } catch (error) {
      throw new Error('Navidrome returned an invalid response.');
    }
    const payload = data && data['subsonic-response'];
    if (!payload) {
      throw new Error('Navidrome response was missing data.');
    }
    if (payload.status !== 'ok') {
      const message = payload.error?.message || 'Navidrome rejected the request.';
      throw new Error(message);
    }
    return payload;
  }

  async fetchCoverArt(id) {
    if (!id) {
      return null;
    }
    const query = this.buildParams({ id }, { json: false });
    let response;
    try {
      response = await fetch(`${this.base}/getCoverArt?${query.toString()}`, {
        method: 'GET',
      });
    } catch (error) {
      throw new Error('Unable to fetch cover art from Navidrome.');
    }
    if (!response.ok) {
      throw new Error(`Navidrome cover art unavailable (status ${response.status}).`);
    }
    return response.blob();
  }

  async ping() {
    await this.requestJson('ping');
    return true;
  }
}
