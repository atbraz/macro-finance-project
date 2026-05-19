"""Events derivable from a calendar alone: ISM, quad witching, Russell, AGG."""
from __future__ import annotations

import datetime as dt
import logging
from datetime import date, time
from typing import Iterable

import pandas as pd
import polars as pl
import pytz
from pandas.tseries.holiday import USFederalHolidayCalendar
from pandas.tseries.offsets import CustomBusinessDay

from ..config import DET_FORWARD_YEARS, DET_START
from ..schema import from_rows

log = logging.getLogger(__name__)

_BDAY = CustomBusinessDay(calendar=USFederalHolidayCalendar())
_ET   = pytz.timezone("America/New_York")
SOURCE = "computed"
SOURCE_URL = "internal://deterministic"


# ---- date helpers --------------------------------------------------------
def _nth_business_day(year: int, month: int, n: int) -> date:
    first = pd.Timestamp(year=year, month=month, day=1)
    bd1 = _BDAY.rollforward(first)
    return (bd1 + (n - 1) * _BDAY).date()


def _last_business_day(year: int, month: int) -> date:
    nm = pd.Timestamp(year=year + (month == 12), month=(month % 12) + 1, day=1)
    return _BDAY.rollback(nm - pd.Timedelta(days=1)).date()


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """weekday: 0=Mon .. 4=Fri. n=1 first, n=2 second, ..."""
    first = pd.Timestamp(year=year, month=month, day=1)
    offset = (weekday - first.dayofweek) % 7
    return (first + pd.Timedelta(days=offset + 7 * (n - 1))).date()


def _last_weekday(year: int, month: int, weekday: int) -> date:
    nm = pd.Timestamp(year=year + (month == 12), month=(month % 12) + 1, day=1)
    last = nm - pd.Timedelta(days=1)
    back = (last.dayofweek - weekday) % 7
    return (last - pd.Timedelta(days=back)).date()


def _et_to_utc(d: date, t: time | None) -> dt.datetime | None:
    if t is None:
        return None
    return _ET.localize(dt.datetime.combine(d, t)).astimezone(pytz.UTC)


# ---- generators ----------------------------------------------------------
def _months(start: date, end: date) -> Iterable[tuple[int, int]]:
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        m += 1
        if m > 12:
            m = 1; y += 1


def _quarter_months() -> set[int]:
    return {3, 6, 9, 12}


def fetch() -> pl.DataFrame:
    start = date.fromisoformat(DET_START)
    end = date.today() + dt.timedelta(days=365 * DET_FORWARD_YEARS)
    now_utc = dt.datetime.now(dt.timezone.utc)
    rows: list[dict] = []

    for y, m in _months(start, end):
        period = f"{y:04d}-{m:02d}"

        ism_m_date = _nth_business_day(y, m, 1)
        rows.append({
            "event_id":              f"ism_mfg_{ism_m_date.isoformat()}",
            "event_name":            "ISM Manufacturing PMI",
            "event_category":        "survey",
            "release_date":          ism_m_date,
            "release_time_et":       time(10, 0),
            "release_timestamp_utc": _et_to_utc(ism_m_date, time(10, 0)),
            "period":                period,
            "tier":                  2,
            "source":                SOURCE,
            "source_url":            SOURCE_URL,
            "scraped_at":            now_utc,
            "notes":                 "1st business day of month",
        })

        ism_s_date = _nth_business_day(y, m, 3)
        rows.append({
            "event_id":              f"ism_svc_{ism_s_date.isoformat()}",
            "event_name":            "ISM Services PMI",
            "event_category":        "survey",
            "release_date":          ism_s_date,
            "release_time_et":       time(10, 0),
            "release_timestamp_utc": _et_to_utc(ism_s_date, time(10, 0)),
            "period":                period,
            "tier":                  2,
            "source":                SOURCE,
            "source_url":            SOURCE_URL,
            "scraped_at":            now_utc,
            "notes":                 "3rd business day of month",
        })

        agg_date = _last_business_day(y, m)
        rows.append({
            "event_id":              f"agg_extension_{agg_date.isoformat()}",
            "event_name":            "AGG Month-End Index Extension",
            "event_category":        "treasury_admin",
            "release_date":          agg_date,
            "release_time_et":       None,
            "release_timestamp_utc": None,
            "period":                period,
            "tier":                  4,
            "source":                SOURCE,
            "source_url":            SOURCE_URL,
            "scraped_at":            now_utc,
            "notes":                 "last business day; duration extension",
        })

        if m in _quarter_months():
            qw = _nth_weekday(y, m, weekday=4, n=3)
            rows.append({
                "event_id":              f"quad_witching_{qw.isoformat()}",
                "event_name":            "Quad Witching",
                "event_category":        "treasury_admin",
                "release_date":          qw,
                "release_time_et":       None,
                "release_timestamp_utc": None,
                "period":                f"{y} Q{(m // 3)}",
                "tier":                  4,
                "source":                SOURCE,
                "source_url":            SOURCE_URL,
                "scraped_at":            now_utc,
                "notes":                 "3rd Friday of quarterly month",
            })

        if m == 6:
            rr = _last_weekday(y, m, weekday=4)
            rows.append({
                "event_id":              f"russell_rebal_{rr.isoformat()}",
                "event_name":            "Russell Rebalance",
                "event_category":        "treasury_admin",
                "release_date":          rr,
                "release_time_et":       None,
                "release_timestamp_utc": None,
                "period":                f"{y}",
                "tier":                  4,
                "source":                SOURCE,
                "source_url":            SOURCE_URL,
                "scraped_at":            now_utc,
                "notes":                 "last Friday of June",
            })

    return from_rows(rows).filter(
        (pl.col("release_date") >= start) & (pl.col("release_date") <= end)
    )
