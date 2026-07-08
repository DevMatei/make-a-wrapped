"""Tests for the ListenBrainz aggregation path used by custom date ranges."""

from __future__ import annotations

import datetime as _dt
import unittest
from unittest.mock import patch

from wrapped_fm import date_range, listenbrainz


REFERENCE = _dt.datetime(2025, 7, 8, 12, 0, tzinfo=_dt.timezone.utc)


def _listen(artist, track, listened_at, release=None, recording_mbid=None, release_mbid=None, artist_mbid=None):
    additional = {}
    if recording_mbid:
        additional["recording_mbid"] = recording_mbid
    if release_mbid:
        additional["release_mbid"] = release_mbid
    if artist_mbid:
        additional["artist_mbids"] = [artist_mbid]
    return {
        "listened_at": listened_at,
        "track_metadata": {
            "artist_name": artist,
            "track_name": track,
            "release_name": release,
            "additional_info": additional,
        },
    }


class _StubResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.ok = 200 <= status_code < 300

    def json(self):
        return self._payload


class ListenBrainzAggregationTests(unittest.TestCase):
    def setUp(self):
        listenbrainz.listenbrainz_cache.clear()
        listenbrainz.aggregation_cache.clear()

    def _patched_session(self, pages):
        queue = iter([_StubResponse(p) for p in pages])

        def fake_get(url, params=None, timeout=None):
            try:
                return next(queue)
            except StopIteration:
                return _StubResponse({"payload": {"listens": []}}, status_code=204)

        return patch.object(listenbrainz.listenbrainz_aggregate_session, "get", side_effect=fake_get)

    def test_aggregate_listens_in_range_uses_pagination(self):
        start = int(_dt.datetime(2025, 6, 1, tzinfo=_dt.timezone.utc).timestamp())
        end = int(_dt.datetime(2025, 7, 1, tzinfo=_dt.timezone.utc).timestamp())
        span = end - start - 60
        all_timestamps = [start + (i * span) // 1500 for i in range(1500)]
        page1_desc = sorted(all_timestamps[-1000:], reverse=True)
        page2_desc = sorted(all_timestamps[:500], reverse=True)
        page1_listens = [_listen("Alpha", f"Track {ts}", ts) for ts in page1_desc]
        page2_listens = [_listen("Alpha", f"Track {ts}", ts) for ts in page2_desc]
        pages = [
            {"payload": {"listens": page1_listens}},
            {"payload": {"listens": page2_listens}},
        ]
        range_obj = date_range.DateRange(
            preset="specific_month",
            label="June 2025",
            kind="month",
            start_ts=start,
            end_ts=end,
            lb_range=None,
            lastfm_period=None,
            is_custom=True,
        )
        with self._patched_session(pages):
            aggregated = listenbrainz._aggregate_listens_in_range("testuser", range_obj)

        self.assertEqual(aggregated.total_listen_count, 1500)
        self.assertFalse(aggregated.reached_limit)
        self.assertEqual(aggregated.top_artists[0]["artist_name"], "Alpha")
        self.assertEqual(aggregated.top_artists[0]["listen_count"], 1500)

    def test_aggregate_skips_listens_outside_window(self):
        start = int(_dt.datetime(2025, 6, 1, tzinfo=_dt.timezone.utc).timestamp())
        end = int(_dt.datetime(2025, 7, 1, tzinfo=_dt.timezone.utc).timestamp())
        outside_before = start - 1000
        outside_after = end + 1000
        listens = [
            _listen("Inside", "T1", start + 100),
            _listen("Before", "T2", outside_before),
            _listen("After", "T3", outside_after),
        ]
        pages = [{"payload": {"listens": listens}}]
        range_obj = date_range.DateRange(
            preset="specific_month",
            label="June 2025",
            kind="month",
            start_ts=start,
            end_ts=end,
            lb_range=None,
            lastfm_period=None,
            is_custom=True,
        )
        with self._patched_session(pages):
            aggregated = listenbrainz._aggregate_listens_in_range("testuser", range_obj)

        self.assertEqual(aggregated.total_listen_count, 1)
        self.assertEqual(aggregated.top_artists[0]["artist_name"], "Inside")

    def test_aggregate_payload_shape_for_artists(self):
        start = int(_dt.datetime(2025, 6, 1, tzinfo=_dt.timezone.utc).timestamp())
        end = int(_dt.datetime(2025, 7, 1, tzinfo=_dt.timezone.utc).timestamp())
        listens = [
            _listen("Alpha", "T1", start + 100),
            _listen("Alpha", "T2", start + 200),
            _listen("Beta", "T3", start + 300),
        ]
        range_obj = date_range.DateRange(
            preset="specific_month",
            label="June 2025",
            kind="month",
            start_ts=start,
            end_ts=end,
            lb_range=None,
            lastfm_period=None,
            is_custom=True,
        )
        with self._patched_session([{"payload": {"listens": listens}}]):
            payload = listenbrainz._aggregate_payload_for_range("testuser", "artists", range_obj)
        self.assertIn("artists", payload)
        self.assertEqual(payload["artists"][0]["artist_name"], "Alpha")
        self.assertEqual(payload["artists"][0]["listen_count"], 2)
        self.assertEqual(payload["_meta"]["total_listen_count"], 3)
        self.assertFalse(payload["_meta"]["reached_limit"])

    def test_aggregate_respects_count_limit(self):
        start = int(_dt.datetime(2025, 6, 1, tzinfo=_dt.timezone.utc).timestamp())
        end = int(_dt.datetime(2025, 7, 1, tzinfo=_dt.timezone.utc).timestamp())
        listens = [_listen(f"Artist {i}", f"Track {i}", start + i) for i in range(20)]
        range_obj = date_range.DateRange(
            preset="specific_month",
            label="June 2025",
            kind="month",
            start_ts=start,
            end_ts=end,
            lb_range=None,
            lastfm_period=None,
            is_custom=True,
        )
        with self._patched_session([{"payload": {"listens": listens}}]):
            payload = listenbrainz._aggregate_payload_for_range("testuser", "artists", range_obj, count=5)
        self.assertEqual(len(payload["artists"]), 5)


if __name__ == "__main__":
    unittest.main()

