function getRangeWindow(range) {
  if (!range || !Number.isFinite(range.startTs) || !Number.isFinite(range.endTs)) {
    const year = new Date().getUTCFullYear();
    const start = Date.UTC(year, 0, 1);
    const end = Date.UTC(year + 1, 0, 1);
    return { start, end };
  }
  return { start: range.startTs * 1000, end: range.endTs * 1000 };
}

function collectArtists(meta) {
  const artist = meta.artist || '';
  if (artist) {
    return [{ id: meta.artistId || '', name: artist }];
  }
  const participants = meta.participants || {};
  const list = Array.isArray(participants.artist) && participants.artist.length
    ? participants.artist
    : null;
  if (list) {
    return list.map((entry) => ({ id: entry.id || '', name: entry.name || '' }));
  }
  return [{ id: '', name: '' }];
}

async function fetchSongMetadata(nativeApi, ids) {
  return nativeApi.fetchSongs(ids);
}

export async function collectNavidromeStatsNative(nativeApi, progressCallback = () => {}, range = null) {
  const { start: rangeStartMs, end: rangeEndMs } = getRangeWindow(range);
  const startTs = Math.floor(rangeStartMs / 1000);
  const endTs = Math.floor(rangeEndMs / 1000);

  progressCallback(2, 'Connecting via the Native API', 'native');
  await nativeApi.authenticate();

  progressCallback(8, 'Fetching scrobble history', 'native');
  const scrobbles = await nativeApi.fetchScrobbles(startTs, endTs);

  const playCounts = new Map();
  let scrobblesInRange = 0;
  for (const scrobble of scrobbles) {
    const submissionTime = Number(scrobble.submissionTime);
    if (!Number.isFinite(submissionTime) || submissionTime < startTs || submissionTime >= endTs) {
      continue;
    }
    scrobblesInRange += 1;
    const fileId = scrobble.mediaFileId;
    if (!fileId) {
      continue;
    }
    playCounts.set(fileId, (playCounts.get(fileId) || 0) + 1);
  }

  const fileIds = [...playCounts.keys()];
  progressCallback(20, `Resolving metadata for ${fileIds.length} tracks`, 'native');
  const metadata = await fetchSongMetadata(nativeApi, fileIds);

  const artistPlays = new Map();
  const artistIdToName = new Map();
  const genrePlayCounts = Object.create(null);
  const albumPlayCounts = new Map();
  const topSongs = [];
  let totalSec = 0;
  let resolved = 0;

  for (const fileId of fileIds) {
    const plays = playCounts.get(fileId) || 0;
    const meta = metadata.get(fileId);
    resolved += 1;
    if (!meta) {
      continue;
    }
    const duration = Number(meta.duration) || 0;
    const genre = (meta.genre || '').trim();
    const albumId = meta.albumId || null;
    const coverArtId = albumId || null;

    for (const artist of collectArtists(meta)) {
      const key = artist.id || artist.name;
      const label = artist.name || 'Unknown artist';
      if (!key) {
        continue;
      }
      artistIdToName.set(key, label);
      artistPlays.set(key, (artistPlays.get(key) || 0) + plays);
    }

    topSongs.push({
      title: meta.title || '',
      plays,
      albumId,
      coverArtId,
    });

    if (albumId) {
      const entry = albumPlayCounts.get(albumId) || {
        plays: 0,
        name: meta.album || '',
        coverArtId,
      };
      entry.plays += plays;
      albumPlayCounts.set(albumId, entry);
    }

    if (genre) {
      genrePlayCounts[genre] = (genrePlayCounts[genre] || 0) + plays;
    }
    totalSec += duration * plays;

    if (resolved % 50 === 0 || resolved === fileIds.length) {
      progressCallback(
        Math.min(90, 20 + (resolved / Math.max(1, fileIds.length)) * 60),
        `Resolved ${resolved} of ${fileIds.length} tracks`,
        'native',
      );
    }
  }

  progressCallback(92, 'Building final objects', 'wrap');

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
    username: nativeApi.user,
    scrobbleCount: scrobblesInRange,
    listeningTime: totalSec,
    topArtistsByPlays: sortedArtists,
    topSongsByPlaycount: sortedSongs,
    topAlbumsByPlaycount: sortedAlbums,
    albumBasedStats: {
      topGenresByPlays,
    },
    period: range || null,
    method: 'experimental',
  };
}
