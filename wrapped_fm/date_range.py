"""Date range presets for Wrapped generation."""

from __future__ import annotations

import calendar
import datetime as _dt
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple


PRESET_THIS_YEAR = "this_year"
PRESET_LAST_YEAR = "last_year"
PRESET_LAST_12_MONTHS = "last_12_months"
PRESET_THIS_MONTH = "this_month"
PRESET_LAST_MONTH = "last_month"
PRESET_SPECIFIC_MONTH = "specific_month"
PRESET_ALL_TIME = "all_time"

YEAR_KIND = "year"
MONTH_KIND = "month"

PRESET_KIND: Dict[str, str] = {
    PRESET_THIS_YEAR: YEAR_KIND,
    PRESET_LAST_YEAR: YEAR_KIND,
    PRESET_LAST_12_MONTHS: YEAR_KIND,
    PRESET_THIS_MONTH: MONTH_KIND,
    PRESET_LAST_MONTH: MONTH_KIND,
    PRESET_SPECIFIC_MONTH: MONTH_KIND,
    PRESET_ALL_TIME: YEAR_KIND,
}

PRESET_LABELS: Dict[str, str] = {
    PRESET_THIS_YEAR: "This year",
    PRESET_LAST_YEAR: "Last year",
    PRESET_LAST_12_MONTHS: "Last 12 months",
    PRESET_THIS_MONTH: "This month",
    PRESET_LAST_MONTH: "Last month",
    PRESET_SPECIFIC_MONTH: "Specific month",
    PRESET_ALL_TIME: "All time",
}

LB_NATIVE_RANGES: Dict[str, str] = {
    PRESET_THIS_YEAR: "this_year",
    PRESET_LAST_YEAR: "year",
    PRESET_THIS_MONTH: "this_month",
    PRESET_LAST_MONTH: "month",
    PRESET_ALL_TIME: "all_time",
}

LASTFM_NATIVE_PERIODS: Dict[str, str] = {
    PRESET_THIS_YEAR: "12month",
    PRESET_THIS_MONTH: "1month",
    PRESET_ALL_TIME: "overall",
}


@dataclass(frozen=True)
class DateRange:
    preset: str
    label: str
    kind: str
    start_ts: int
    end_ts: int
    lb_range: Optional[str]
    lastfm_period: Optional[str]
    is_custom: bool

    @property
    def start_iso(self) -> str:
        return _dt.datetime.fromtimestamp(self.start_ts, tz=_dt.timezone.utc).strftime("%Y-%m-%d")

    @property
    def end_iso(self) -> str:
        return _dt.datetime.fromtimestamp(self.end_ts, tz=_dt.timezone.utc).strftime("%Y-%m-%d")


def _utc_now() -> _dt.datetime:
    return _dt.datetime.now(tz=_dt.timezone.utc)


def _year_range(year: int) -> Tuple[int, int]:
    start = int(_dt.datetime(year, 1, 1, tzinfo=_dt.timezone.utc).timestamp())
    end = int(_dt.datetime(year + 1, 1, 1, tzinfo=_dt.timezone.utc).timestamp())
    return start, end


def _month_range(year: int, month: int) -> Tuple[int, int]:
    last_day = calendar.monthrange(year, month)[1]
    start = int(_dt.datetime(year, month, 1, tzinfo=_dt.timezone.utc).timestamp())
    end = int(_dt.datetime(year, month, last_day, 23, 59, 59, tzinfo=_dt.timezone.utc).timestamp()) + 1
    return start, end


def _last_12_months_range(now: _dt.datetime) -> Tuple[int, int]:
    end = int(now.timestamp())
    start = int((now - _dt.timedelta(days=365)).timestamp())
    return start, end


def _max_listen_timestamp(now: _dt.datetime) -> int:
    return int(now.timestamp())


def list_presets() -> List[Dict[str, str]]:
    return [
        {"value": preset, "label": PRESET_LABELS[preset], "kind": kind}
        for preset, kind in PRESET_KIND.items()
    ]


def list_months() -> List[Dict[str, str]]:
    return [
        {"value": str(month), "label": _dt.date(2000, month, 1).strftime("%B")}
        for month in range(1, 13)
    ]


def list_years(span: int = 10, reference: Optional[_dt.datetime] = None) -> List[int]:
    now = reference or _utc_now()
    return [now.year - offset for offset in range(span)]


def resolve_preset(
    preset: str,
    *,
    month: Optional[int] = None,
    year: Optional[int] = None,
    reference: Optional[_dt.datetime] = None,
) -> DateRange:
    if preset not in PRESET_KIND:
        raise ValueError(f"unknown period preset: {preset!r}")

    now = reference or _utc_now()
    kind = PRESET_KIND[preset]
    is_custom = preset not in LB_NATIVE_RANGES or preset not in LASTFM_NATIVE_PERIODS

    if preset == PRESET_THIS_YEAR:
        start_ts, end_ts = _year_range(now.year)
        end_ts = min(end_ts, _max_listen_timestamp(now))
    elif preset == PRESET_LAST_YEAR:
        start_ts, end_ts = _year_range(now.year - 1)
    elif preset == PRESET_LAST_12_MONTHS:
        start_ts, end_ts = _last_12_months_range(now)
    elif preset == PRESET_THIS_MONTH:
        start_ts, end_ts = _month_range(now.year, now.month)
        end_ts = min(end_ts, _max_listen_timestamp(now))
    elif preset == PRESET_LAST_MONTH:
        last_month_ref = (now.replace(day=1) - _dt.timedelta(days=1))
        start_ts, end_ts = _month_range(last_month_ref.year, last_month_ref.month)
    elif preset == PRESET_ALL_TIME:
        end_ts = _max_listen_timestamp(now)
        start_ts = 0
    elif preset == PRESET_SPECIFIC_MONTH:
        if month is None or year is None:
            raise ValueError("specific month requires both month and year")
        if not 1 <= int(month) <= 12:
            raise ValueError(f"invalid month: {month!r}")
        month_i = int(month)
        year_i = int(year)
        start_ts, end_ts = _month_range(year_i, month_i)
        first_of_current_month = _dt.datetime(now.year, now.month, 1, tzinfo=_dt.timezone.utc)
        if start_ts > first_of_current_month.timestamp():
            raise ValueError("specific month can't be in the future")
        if (year_i, month_i) == (now.year, now.month):
            end_ts = min(end_ts, _max_listen_timestamp(now))
    else:
        raise ValueError(f"unknown period preset: {preset!r}")

    label = _build_label(preset, month, year)
    return DateRange(
        preset=preset,
        label=label,
        kind=kind,
        start_ts=start_ts,
        end_ts=end_ts,
        lb_range=LB_NATIVE_RANGES.get(preset),
        lastfm_period=LASTFM_NATIVE_PERIODS.get(preset),
        is_custom=is_custom,
    )


def _build_label(preset: str, month: Optional[int], year: Optional[int]) -> str:
    if preset != PRESET_SPECIFIC_MONTH:
        return PRESET_LABELS[preset]
    if month is None or year is None:
        return PRESET_LABELS[preset]
    month_name = _dt.date(int(year), int(month), 1).strftime("%B")
    return f"{month_name} {year}"


def describe_for_client(reference: Optional[_dt.datetime] = None) -> Dict[str, object]:
    reference = reference or _utc_now()
    return {
        "presets": list_presets(),
        "months": list_months(),
        "years": list_years(reference=reference),
        "defaults": {
            "preset": PRESET_THIS_YEAR,
            "month": reference.month,
            "year": reference.year,
        },
        "maxSpecificMonth": {
            "month": reference.month,
            "year": reference.year,
        },
    }


def parse_query_params(args: Iterable[Tuple[str, str]]) -> DateRange:
    params: Dict[str, str] = {str(k): str(v) for k, v in args if v is not None}
    preset = (params.get("range") or params.get("preset") or PRESET_THIS_YEAR).strip().lower()
    month_raw = params.get("month")
    year_raw = params.get("year")
    try:
        month = int(month_raw) if month_raw not in (None, "") else None
        year = int(year_raw) if year_raw not in (None, "") else None
        return resolve_preset(preset, month=month, year=year)
    except ValueError:
        return resolve_preset(PRESET_THIS_YEAR)
