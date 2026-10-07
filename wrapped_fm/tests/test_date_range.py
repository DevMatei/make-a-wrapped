"""Tests for the date range preset resolver."""

from __future__ import annotations

import datetime as _dt
import unittest

from wrapped_fm.date_range import (
    MONTH_KIND,
    YEAR_KIND,
    describe_for_client,
    list_presets,
    parse_query_params,
    resolve_preset,
)


REFERENCE = _dt.datetime(2025, 7, 8, 12, 0, tzinfo=_dt.timezone.utc)


class ResolvePresetTests(unittest.TestCase):
    def test_presets_resolve_to_expected_windows(self):
        cases = [
            ("this_year", {}, "2025-01-01", "2025-07-08", "this_year", False, YEAR_KIND),
            ("last_year", {}, "2024-01-01", "2025-01-01", "year", True, YEAR_KIND),
            ("last_12_months", {}, "2024-07-08", "2025-07-08", None, True, None),
            ("this_month", {}, "2025-07-01", "2025-07-08", "this_month", False, MONTH_KIND),
            ("last_month", {}, "2025-06-01", "2025-07-01", "month", True, MONTH_KIND),
            ("specific_month", {"month": 3, "year": 2024}, "2024-03-01", "2024-04-01", None, True, MONTH_KIND),
            ("specific_month", {"month": 7, "year": 2025}, "2025-07-01", "2025-07-08", None, True, MONTH_KIND),
            ("all_time", {}, "1970-01-01", "2025-07-08", "all_time", False, None),
        ]

        for preset, extra, start, end, lb_range, is_custom, kind in cases:
            with self.subTest(preset=preset, **extra):
                result = resolve_preset(preset, reference=REFERENCE, **extra)

                self.assertEqual(result.preset, preset)
                self.assertEqual((result.start_iso, result.end_iso), (start, end))
                self.assertEqual(result.lb_range, lb_range)
                self.assertEqual(result.is_custom, is_custom)
                if kind:
                    self.assertEqual(result.kind, kind)

        self.assertEqual(resolve_preset("specific_month", month=3, year=2024, reference=REFERENCE).label, "March 2024")

    def test_rejects_invalid_presets(self):
        cases = [
            ("unknown", "nope", {}),
            ("future month", "specific_month", {"month": 1, "year": 2030}),
            ("missing month", "specific_month", {}),
            ("month out of range", "specific_month", {"month": 13, "year": 2025}),
            ("bad year", "specific_month", {"month": 5, "year": "not-a-year"}),
        ]

        for name, preset, extra in cases:
            with self.subTest(name=name), self.assertRaises(ValueError):
                resolve_preset(preset, reference=REFERENCE, **extra)

    def test_client_descriptor_lists_every_preset(self):
        descriptor = describe_for_client(reference=REFERENCE)

        self.assertEqual(
            {entry["value"] for entry in list_presets()},
            {"this_year", "last_year", "last_12_months", "this_month", "last_month", "specific_month", "all_time"},
        )
        self.assertTrue({"presets", "months", "years", "defaults", "maxSpecificMonth"} <= set(descriptor))
        self.assertEqual(descriptor["defaults"]["preset"], "this_year")
        self.assertEqual(descriptor["maxSpecificMonth"], {"month": 7, "year": 2025})

    def test_parse_query_params_reads_range_and_falls_back(self):
        result = parse_query_params([("range", "specific_month"), ("month", "5"), ("year", "2024")])

        self.assertEqual((result.preset, result.start_iso), ("specific_month", "2024-05-01"))
        self.assertEqual(parse_query_params([("range", "garbage")]).preset, "this_year")


if __name__ == "__main__":
    unittest.main()
