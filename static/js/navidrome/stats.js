import {
  NAVIDROME_SONG_PAGE_SIZE,
  NAVIDROME_REQUEST_DELAY_MS,
  NAVIDROME_CONCURRENT_REQUESTS,
} from './constants.js';
import { delay } from './helpers.js';

function getCurrentYearRange(referenceDate = new Date()) {
  const year = referenceDate.getUTCFullYear();
  const start = Date.UTC(year, 0, 1);
  const end = Date.UTC(year + 1, 0, 1);
  return { year, start, end };
}

function getRangeWindow(range) {
  if (!range || !Number.isFinite(range.startTs) || !Number.isFinite(range.endTs)) {
    return getCurrentYearRange();
  }
  return { start: range.startTs * 1000, end: range.endTs * 1000 };
}

function parsePlayDate(value) {
  if (!value && value !== 0) {
    return null;
  }
  if (value instanceof Date) {
    const time = value.getTime();
    return Number.isFinite(time) ? time : null;
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value > 1e12 ? value : value * 1000;
  }
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed) {
      return null;
    }
    const parsed = Date.parse(trimmed);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function isWithinRange(timestamp, start, end) {
  if (!Number.isFinite(timestamp)) {
    return false;
  }
  return timestamp >= start && timestamp < end;
}

async function fetchSongsBatch(api, offset, size) {
  const payload = await api.requestJson('search3', {
    query: '',
    songCount: String(size),
    songOffset: String(offset),
    albumCount: '0',
    artistCount: '0',
  });
  return payload?.searchResult3?.song || [];
}

export async function collectNavidromeStats(api, progressCallback = () => {}, range = null) {
  const artistPlays = new Map();
  const artistIdToName = new Map();
  const genrePlayCounts = Object.create(null);
  const albumPlayCounts = new Map();
  const topSongs = [];
  const { start: rangeStartMs, end: rangeEndMs } = getRangeWindow(range);
  let totalSec = 0;
  let totalSongsFetched = 0;
  let nextOffset = 0;
  let reachedEnd = false;

  progressCallback(0, 'Starting song scan', 'songs');

  function processSong(song) {
    const playCount = Number(song.playCount) || 0;
    if (!playCount) {
      return;
    }

    const playDateRaw = song.playDate || song.played || song.lastPlayed || null;
    const playedAt = parsePlayDate(playDateRaw);
    if (!isWithinRange(playedAt, rangeStartMs, rangeEndMs)) {
      return;
    }

    const duration = Number(song.duration) || 0;
    const artistName = song.displayArtist || song.artist || '';
    const genre = (song.genre || '').trim();
    const coverArt = song.coverArt || null;
    const albumId = song.albumId || null;
    const artistsArr = Array.isArray(song.artists) && song.artists.length
      ? song.artists
      : [{ id: song.artistId || '', name: artistName }];

    artistsArr.forEach((entry) => {
      const artistKey = entry.id || entry.name || artistName;
      const artistLabel = entry.name || artistName || 'Unknown artist';
      if (!artistKey && !artistLabel) {
        return;
      }
      const key = artistKey || artistLabel;
      artistIdToName.set(key, artistLabel);
      if (playCount > 0) {
        artistPlays.set(key, (artistPlays.get(key) || 0) + playCount);
      }
    });

    topSongs.push({
      title: song.title || '',
      plays: playCount,
      albumId,
      coverArtId: coverArt,
    });

    if (albumId) {
      const albumEntry = albumPlayCounts.get(albumId) || {
        plays: 0,
        name: song.album || '',
        coverArtId: coverArt,
      };
      albumEntry.plays += playCount;
      if (!albumEntry.coverArtId && coverArt) {
        albumEntry.coverArtId = coverArt;
      }
      albumPlayCounts.set(albumId, albumEntry);
    }

    if (genre) {
      genrePlayCounts[genre] = (genrePlayCounts[genre] || 0) + playCount;
    }
    if (playCount) {
      totalSec += duration * playCount;
    }
  }

  async function fetchAndProcessBatch(offset) {
    const batch = await fetchSongsBatch(api, offset, NAVIDROME_SONG_PAGE_SIZE);
    if (!batch.length) {
      reachedEnd = true;
      return 0;
    }
    for (const song of batch) {
      processSong(song);
    }
    totalSongsFetched += batch.length;
    const progress = Math.min(90, (totalSongsFetched / 10000) * 80);
    progressCallback(progress, `Fetched ${totalSongsFetched} songs`, 'songs');
    return batch.length;
  }

  async function runWithConcurrency() {
    const activePromises = new Set();

    while (!reachedEnd) {
      while (activePromises.size < NAVIDROME_CONCURRENT_REQUESTS && !reachedEnd) {
        const offset = nextOffset;
        nextOffset += NAVIDROME_SONG_PAGE_SIZE;

        const promise = fetchAndProcessBatch(offset)
          .catch((error) => {
            console.error('Batch fetch error:', error);
            reachedEnd = true;
            return 0;
          })
          .finally(() => {
            activePromises.delete(promise);
          });

        activePromises.add(promise);
        await delay(NAVIDROME_REQUEST_DELAY_MS);
      }

      if (activePromises.size) {
        await Promise.race(activePromises);
      }
    }

    if (activePromises.size) {
      await Promise.allSettled(activePromises);
    }
  }

  await runWithConcurrency();

  progressCallback(90, 'Building final objects', 'wrap');

  const sortedArtists = [...artistPlays.entries()]
    .filter(([id]) => (artistIdToName.get(id) || id).toLowerCase() !== 'various artists')
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([id, plays]) => [artistIdToName.get(id) || id, plays]);

  const sortedSongs = topSongs
    .filter((song) => song.plays)
    .sort((a, b) => b.plays - a.plays)
    .slice(0, 10)
    .map((song) => ({
      title: song.title || 'Unknown track',
      coverArtId: song.coverArtId || null,
      albumId: song.albumId || null,
    }));

  const sortedAlbums = [...albumPlayCounts.entries()]
    .sort((a, b) => b[1].plays - a[1].plays)
    .slice(0, 10)
    .map(([id, entry]) => ({
      name: entry.name || 'Unknown album',
      id,
      coverArtId: entry.coverArtId || null,
    }));

  const topGenresByPlays = Object.entries(genrePlayCounts).sort((a, b) => b[1] - a[1]).slice(0, 5);

  progressCallback(100, 'Done', 'complete');

  return {
    username: api.user,
    listeningTime: totalSec,
    topArtistsByPlays: sortedArtists,
    topSongsByPlaycount: sortedSongs,
    topAlbumsByPlaycount: sortedAlbums,
    albumBasedStats: {
      topGenresByPlays,
    },
    period: range || null,
  };
}
