import { NavidromeApi } from './navidrome/api.js';
import { collectNavidromeStats } from './navidrome/stats.js';

export class NavidromeClient {
  constructor(serverUrl, username, password) {
    this.api = new NavidromeApi(serverUrl, username, password);
  }

  async ping() {
    return this.api.ping();
  }

  async fetchCoverArt(id) {
    return this.api.fetchCoverArt(id);
  }

  async stats(progressCallback = () => {}, range = null) {
    return collectNavidromeStats(this.api, progressCallback, range);
  }
}
