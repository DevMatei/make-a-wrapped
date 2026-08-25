import { NavidromeApi } from './navidrome/api.js';
import { NavidromeNativeApi } from './navidrome/native-api.js';
import { collectNavidromeStats } from './navidrome/stats.js';
import { collectNavidromeStatsNative } from './navidrome/stats-native.js';

export class NavidromeClient {
  constructor(serverUrl, username, password, method = 'legacy') {
    this.api = new NavidromeApi(serverUrl, username, password);
    this.method = method;
    this.nativeApi = method === 'experimental'
      ? new NavidromeNativeApi(serverUrl, username, password)
      : null;
  }

  async ping() {
    return this.api.ping();
  }

  async fetchCoverArt(id) {
    return this.api.fetchCoverArt(id);
  }

  async stats(progressCallback = () => {}, range = null) {
    if (this.method === 'experimental') {
      return collectNavidromeStatsNative(this.nativeApi, progressCallback, range);
    }
    return collectNavidromeStats(this.api, progressCallback, range);
  }
}
