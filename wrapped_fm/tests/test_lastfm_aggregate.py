"""Tests for the Last.fm aggregation path used by custom date ranges."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from wrapped_fm import date_range, lastfm


def _recent(artist, track, album, uts):
    return {
        "name": track,
        "artist": {"#text": artist},
        "album": {"#text": album},
        "date": {"uts": str(uts)},
    }


class _StubResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.ok = 200 <= status_code < 300

    def json(self):
        return self._payload


class LastfmAggregationTests(unittest.TestCase):
    def setUp(self):
        lastfm.recenttracks_cache.clear()

    def test_aggregate_recent_paginates_with_from_to(self):
        start = 1_700_000_000
        end = start + 3600
        page1 = [_recent("Alpha", f"T{i}", "Album", end - 1 - i * 5) for i in range(200)]
        page2 = [_recent("Beta", "Older Track", "Album", start + 30)]

        responses = iter([
            {"recenttracks": {"track": page1}},
            {"recenttracks": {"track": page2}},
        ])

        def fake_get(url, params=None, timeout=None):
            try:
                return _StubResponse(next(responses))
            except StopIteration:
                return _StubResponse({"recenttracks": {"track": []}})

        range_obj = date_range.DateRange(
            preset="specific_month",
            label="Nov 2023",
            kind="month",
            start_ts=start,
            end_ts=end,
            lb_range=None,
            lastfm_period=None,
            is_custom=True,
        )
        with patch.object(lastfm.lastfm_aggregate_session, "get", side_effect=fake_get):
            aggregated = lastfm._aggregate_recent_in_range("testuser", range_obj)

        self.assertEqual(aggregated.total_listen_count, 201)
        self.assertEqual(aggregated.top_artists[0][0], "Alpha")
        self.assertEqual(aggregated.top_artists[0][1], 200)
        self.assertIn("Beta", [name for name, _ in aggregated.top_artists])

    def test_top_artists_uses_native_period_for_supported_presets(self):
        called = []

        def fake_call(method, params=None):
            called.append((method, params))
            return {"topartists": {"artist": [{"name": "Alpha"}]}}

        with patch.object(lastfm, "_call_lastfm", side_effect=fake_call):
            names = lastfm.get_lastfm_top_artists("u", 5, range_obj=date_range.resolve_preset("this_year"))

        self.assertEqual(names, ["Alpha"])
        self.assertEqual(called[0][0], "user.gettopartists")
        self.assertEqual(called[0][1]["period"], "12month")

    def test_top_artists_falls_back_to_aggregation_for_custom_presets(self):
        range_obj = date_range.resolve_preset("specific_month", month=11, year=2023)

        def fake_get(url, params=None, timeout=None):
            return _StubResponse({
                "recenttracks": {"track": [_recent("Beta", "T", "Album", 1_700_000_000)]},
            })

        with patch.object(lastfm.lastfm_aggregate_session, "get", side_effect=fake_get):
            names = lastfm.get_lastfm_top_artists("u", 5, range_obj=range_obj)

        self.assertEqual(names, ["Beta"])


if __name__ == "__main__":
    unittest.main()
