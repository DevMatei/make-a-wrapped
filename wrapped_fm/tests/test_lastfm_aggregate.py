"""Tests for the Last.fm aggregation path used by custom date ranges."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from wrapped_fm import date_range, lastfm


def _recent(artist, track, uts):
    return {"name": track, "artist": {"#text": artist}, "album": {"#text": "Album"}, "date": {"uts": str(uts)}}


def _pages(*pages):
    responses = iter(pages)

    def fake_get(url, params=None, timeout=None):
        tracks = next(responses, [])
        return SimpleNamespace(ok=True, status_code=200, json=lambda: {"recenttracks": {"track": tracks}})

    return patch.object(lastfm.lastfm_aggregate_session, "get", side_effect=fake_get)


class LastfmAggregationTests(unittest.TestCase):
    def setUp(self):
        lastfm.recenttracks_cache.clear()

    def test_aggregate_recent_paginates_with_from_to(self):
        start = 1_700_000_000
        end = start + 3600
        range_obj = date_range.DateRange(
            preset="specific_month", label="Nov 2023", kind="month", start_ts=start, end_ts=end,
            lb_range=None, lastfm_period=None, is_custom=True,
        )
        first_page = [_recent("Alpha", f"T{i}", end - 1 - i * 5) for i in range(200)]

        with _pages(first_page, [_recent("Beta", "Older", start + 30)]):
            aggregated = lastfm._aggregate_recent_in_range("testuser", range_obj)

        self.assertEqual(aggregated.total_listen_count, 201)
        self.assertEqual(aggregated.top_artists[0], ("Alpha", 200))
        self.assertIn("Beta", [name for name, _ in aggregated.top_artists])

    def test_top_artists_picks_native_period_or_aggregation(self):
        with patch.object(lastfm, "_call_lastfm", return_value={"topartists": {"artist": [{"name": "Alpha"}]}}) as call:
            native = lastfm.get_lastfm_top_artists("u", 5, range_obj=date_range.resolve_preset("this_year"))
        with _pages([_recent("Beta", "T", 1_700_000_000)]):
            custom = lastfm.get_lastfm_top_artists("u", 5, range_obj=date_range.resolve_preset("specific_month", month=11, year=2023))

        self.assertEqual(native, ["Alpha"])
        self.assertEqual(call.call_args.args[0], "user.gettopartists")
        self.assertEqual(call.call_args.args[1]["period"], "12month")
        self.assertEqual(custom, ["Beta"])


if __name__ == "__main__":
    unittest.main()
