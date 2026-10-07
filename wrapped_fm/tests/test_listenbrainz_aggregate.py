"""Tests for the ListenBrainz aggregation path used by custom date ranges."""

from __future__ import annotations

import datetime as _dt
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from wrapped_fm import date_range, listenbrainz


START = int(_dt.datetime(2025, 6, 1, tzinfo=_dt.timezone.utc).timestamp())
END = int(_dt.datetime(2025, 7, 1, tzinfo=_dt.timezone.utc).timestamp())
JUNE = date_range.DateRange(
    preset="specific_month", label="June 2025", kind="month", start_ts=START, end_ts=END,
    lb_range=None, lastfm_period=None, is_custom=True,
)


def _listen(artist, track, listened_at):
    return {
        "listened_at": listened_at,
        "track_metadata": {"artist_name": artist, "track_name": track, "release_name": None, "additional_info": {}},
    }


def _pages(*pages):
    responses = iter(pages)

    def fake_get(url, params=None, timeout=None):
        listens = next(responses, None)
        if listens is None:
            return SimpleNamespace(ok=True, status_code=204, json=lambda: {"payload": {"listens": []}})
        return SimpleNamespace(ok=True, status_code=200, json=lambda: {"payload": {"listens": listens}})

    return patch.object(listenbrainz.listenbrainz_aggregate_session, "get", side_effect=fake_get)


class ListenBrainzAggregationTests(unittest.TestCase):
    def setUp(self):
        listenbrainz.listenbrainz_cache.clear()
        listenbrainz.aggregation_cache.clear()

    def test_aggregate_listens_in_range_uses_pagination(self):
        span = END - START - 60
        timestamps = [START + (i * span) // 1500 for i in range(1500)]
        pages = [sorted(timestamps[-1000:], reverse=True), sorted(timestamps[:500], reverse=True)]

        with _pages(*[[_listen("Alpha", f"Track {ts}", ts) for ts in page] for page in pages]):
            aggregated = listenbrainz._aggregate_listens_in_range("testuser", JUNE)

        self.assertEqual(aggregated.total_listen_count, 1500)
        self.assertFalse(aggregated.reached_limit)
        self.assertEqual(aggregated.top_artists[0]["artist_name"], "Alpha")
        self.assertEqual(aggregated.top_artists[0]["listen_count"], 1500)

    def test_aggregate_payload_filters_window_and_limits_count(self):
        listens = [
            _listen("Alpha", "T1", START + 100),
            _listen("Alpha", "T2", START + 200),
            _listen("Before", "T3", START - 1000),
            _listen("After", "T4", END + 1000),
        ] + [_listen(f"Artist {i}", f"Track {i}", START + 300 + i) for i in range(10)]

        with _pages(listens):
            payload = listenbrainz._aggregate_payload_for_range("testuser", "artists", JUNE, count=5)

        names = [artist["artist_name"] for artist in payload["artists"]]
        self.assertEqual(len(names), 5)
        self.assertEqual((names[0], payload["artists"][0]["listen_count"]), ("Alpha", 2))
        self.assertNotIn("Before", names)
        self.assertNotIn("After", names)
        self.assertEqual(payload["_meta"]["total_listen_count"], 12)
        self.assertFalse(payload["_meta"]["reached_limit"])


if __name__ == "__main__":
    unittest.main()
