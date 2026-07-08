"""Tests for the date range preset resolver."""

from __future__ import annotations

import datetime as _dt
import unittest

from wrapped_fm.date_range import (
    MONTH_KIND,
    PRESET_ALL_TIME,
    PRESET_LAST_12_MONTHS,
    PRESET_LAST_MONTH,
    PRESET_LAST_YEAR,
    PRESET_SPECIFIC_MONTH,
    PRESET_THIS_MONTH,
    PRESET_THIS_YEAR,
    YEAR_KIND,
    describe_for_client,
    list_presets,
    parse_query_params,
    resolve_preset,
)


REFERENCE = _dt.datetime(2025, 7, 8, 12, 0, tzinfo=_dt.timezone.utc)


class ResolvePresetTests(unittest.TestCase):
    def test_this_year_in_progress_clamps_to_now(self):
        result = resolve_preset(PRESET_THIS_YEAR, reference=REFERENCE)
        self.assertEqual(result.preset, PRESET_THIS_YEAR)
        self.assertEqual(result.kind, YEAR_KIND)
        self.assertEqual(result.start_iso, "2025-01-01")
        self.assertEqual(result.end_iso, "2025-07-08")
        self.assertEqual(result.lb_range, "this_year")
        self.assertFalse(result.is_custom)

    def test_last_year_returns_previous_calendar_year(self):
        result = resolve_preset(PRESET_LAST_YEAR, reference=REFERENCE)
        self.assertEqual(result.start_iso, "2024-01-01")
        self.assertEqual(result.end_iso, "2025-01-01")
        self.assertEqual(result.lb_range, "year")
        self.assertTrue(result.is_custom)

    def test_last_12_months_is_rolling_365(self):
        result = resolve_preset(PRESET_LAST_12_MONTHS, reference=REFERENCE)
        self.assertEqual(result.start_iso, "2024-07-08")
        self.assertEqual(result.end_iso, "2025-07-08")
        self.assertIsNone(result.lb_range)
        self.assertTrue(result.is_custom)

    def test_this_month_clamps_to_now(self):
        result = resolve_preset(PRESET_THIS_MONTH, reference=REFERENCE)
        self.assertEqual(result.start_iso, "2025-07-01")
        self.assertEqual(result.end_iso, "2025-07-08")
        self.assertEqual(result.lb_range, "this_month")
        self.assertEqual(result.kind, MONTH_KIND)
        self.assertFalse(result.is_custom)

    def test_last_month_is_previous_calendar_month(self):
        result = resolve_preset(PRESET_LAST_MONTH, reference=REFERENCE)
        self.assertEqual(result.start_iso, "2025-06-01")
        self.assertEqual(result.end_iso, "2025-07-01")
        self.assertEqual(result.lb_range, "month")
        self.assertTrue(result.is_custom)

    def test_specific_month_label_and_bounds(self):
        result = resolve_preset(PRESET_SPECIFIC_MONTH, month=3, year=2024, reference=REFERENCE)
        self.assertEqual(result.label, "March 2024")
        self.assertEqual(result.start_iso, "2024-03-01")
        self.assertEqual(result.end_iso, "2024-04-01")
        self.assertEqual(result.kind, MONTH_KIND)
        self.assertIsNone(result.lb_range)
        self.assertTrue(result.is_custom)

    def test_specific_month_rejects_future(self):
        with self.assertRaises(ValueError):
            resolve_preset(PRESET_SPECIFIC_MONTH, month=1, year=2030, reference=REFERENCE)

    def test_specific_month_allows_current_month_so_far(self):
        result = resolve_preset(PRESET_SPECIFIC_MONTH, month=REFERENCE.month, year=REFERENCE.year, reference=REFERENCE)
        self.assertEqual(result.start_iso, "2025-07-01")
        self.assertEqual(result.end_iso, "2025-07-08")

    def test_specific_month_requires_month_and_year(self):
        with self.assertRaises(ValueError):
            resolve_preset(PRESET_SPECIFIC_MONTH, reference=REFERENCE)
        with self.assertRaises(ValueError):
            resolve_preset(PRESET_SPECIFIC_MONTH, month=13, year=2025, reference=REFERENCE)
        with self.assertRaises(ValueError):
            resolve_preset(PRESET_SPECIFIC_MONTH, month=5, year="not-a-year", reference=REFERENCE)

    def test_unknown_preset_rejected(self):
        with self.assertRaises(ValueError):
            resolve_preset("nope", reference=REFERENCE)

    def test_all_time_preset(self):
        result = resolve_preset(PRESET_ALL_TIME, reference=REFERENCE)
        self.assertEqual(result.start_ts, 0)
        self.assertEqual(result.end_iso, "2025-07-08")
        self.assertEqual(result.lb_range, "all_time")
        self.assertFalse(result.is_custom)

    def test_list_presets_returns_all_six(self):
        presets = list_presets()
        values = {entry["value"] for entry in presets}
        self.assertSetEqual(
            values,
            {
                PRESET_THIS_YEAR,
                PRESET_LAST_YEAR,
                PRESET_LAST_12_MONTHS,
                PRESET_THIS_MONTH,
                PRESET_LAST_MONTH,
                PRESET_SPECIFIC_MONTH,
                PRESET_ALL_TIME,
            },
        )

    def test_describe_for_client_returns_static_shape(self):
        descriptor = describe_for_client(reference=REFERENCE)
        self.assertIn("presets", descriptor)
        self.assertIn("months", descriptor)
        self.assertIn("years", descriptor)
        self.assertIn("defaults", descriptor)
        self.assertIn("maxSpecificMonth", descriptor)
        self.assertEqual(descriptor["defaults"]["preset"], PRESET_THIS_YEAR)
        self.assertEqual(descriptor["maxSpecificMonth"], {"month": 7, "year": 2025})

    def test_parse_query_params_reads_range_aliases(self):
        result = parse_query_params([("range", "specific_month"), ("month", "5"), ("year", "2024")])
        self.assertEqual(result.preset, PRESET_SPECIFIC_MONTH)
        self.assertEqual(result.start_iso, "2024-05-01")
        result = parse_query_params([("range", "garbage")])
        self.assertEqual(result.preset, PRESET_THIS_YEAR)


if __name__ == "__main__":
    unittest.main()
