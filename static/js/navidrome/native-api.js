import { normaliseServerUrl } from './helpers.js';
import {
  NAVIDROME_SCRABBLE_CONCURRENCY,
  NAVIDROME_SCRABBLE_PAGE_SIZE,
} from './constants.js';

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

  async _request(path, params = null) {
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
    return response;
  }

  async _requestJson(path, params = null) {
    const response = await this._request(path, params);
    try {
      return await response.json();
    } catch (error) {
      throw new Error('Navidrome Native API returned an invalid response.');
    }
  }

  async requestJson(path, params = null) {
    return this._requestJson(path, params);
  }

  async _requestArray(path, params = null) {
    const response = await this._request(path, params);
    try {
      const data = await response.json();
      return Array.isArray(data) ? data : [];
    } catch (error) {
      throw new Error('Navidrome Native API returned an invalid response.');
    }
  }

  _scrobbleParams(fromTs, toTs, start, end) {
    return new URLSearchParams({
      from: String(fromTs),
      to: String(toTs),
      _sort: 'submission_time',
      _order: 'asc',
      _start: String(start),
      _end: String(end),
    });
  }

  async fetchScrobbles(fromTs, toTs) {
    const pageSize = NAVIDROME_SCRABBLE_PAGE_SIZE;
    const first = await this._request('/api/scrobble', this._scrobbleParams(fromTs, toTs, 0, pageSize));
    let firstRows;
    try {
      firstRows = await first.json();
    } catch (error) {
      throw new Error('Navidrome Native API returned an invalid response.');
    }
    if (!Array.isArray(firstRows)) {
      firstRows = [];
    }
    if (firstRows.length < pageSize) {
      return firstRows;
    }
    const total = Number(first.headers.get('X-Total-Count'));
    const knownTotal = Number.isFinite(total) && total >= firstRows.length;
    if (!knownTotal) {
      const scrobbles = [...firstRows];
      let offset = pageSize;
      for (;;) {
        const rows = await this._requestArray('/api/scrobble', this._scrobbleParams(fromTs, toTs, offset, offset + pageSize));
        scrobbles.push(...rows);
        if (rows.length < pageSize) {
          break;
        }
        offset += pageSize;
      }
      return scrobbles;
    }
    const totalPages = Math.ceil(total / pageSize);
    const pages = new Array(totalPages);
    pages[0] = firstRows;
    let index = 1;
    const worker = async () => {
      while (index < totalPages) {
        const pageIndex = index;
        index += 1;
        const rows = await this._requestArray(
          '/api/scrobble',
          this._scrobbleParams(fromTs, toTs, pageIndex * pageSize, (pageIndex + 1) * pageSize),
        );
        pages[pageIndex] = rows;
      }
    };
    await Promise.all(
      Array.from({ length: Math.min(NAVIDROME_SCRABBLE_CONCURRENCY, totalPages - 1) }, worker),
    );
    const scrobbles = [];
    for (const page of pages) {
      if (page) {
        scrobbles.push(...page);
      }
    }
    return scrobbles;
  }

  async fetchSong(id) {
    const data = await this._requestJson(`/api/song/${encodeURIComponent(id)}`);
    return data && typeof data === 'object' ? data : null;
  }

  async fetchSongs(ids) {
    const results = new Map();
    const chunkSize = 200;
    const chunks = [];
    for (let i = 0; i < ids.length; i += chunkSize) {
      chunks.push(ids.slice(i, i + chunkSize));
    }
    const worker = async (chunk) => {
      const params = new URLSearchParams();
      for (const id of chunk) {
        params.append('id', id);
      }
      const rows = await this._requestArray('/api/song', params);
      for (const row of rows) {
        if (row && row.id) {
          results.set(row.id, row);
        }
      }
    };
    await Promise.all(chunks.map(worker));
    return results;
  }
}