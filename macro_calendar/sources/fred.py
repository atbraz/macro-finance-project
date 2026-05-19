"""FRED release dates via fredapi. Inert if FRED_API_KEY is unset."""
from __future__ import annotations

import datetime as dt
import logging
from datetime import date, time

import polars as pl
import pytz

from ..config import FRED_API_KEY, FRED_RELEASES
from ..schema import from_rows

log = logging.getLogger(__name__)

SOURCE = "fred"
_ET = pytz.timezone("America/New_York")


def _prior_month_period(d: date) -> str:
    y, m = d.year, d.month - 1
    if m == 0:
        y -= 1; m = 12
    return f"{y:04d}-{m:02d}"


def _et_to_utc(d: date, t: time | None) -> dt.datetime | None:
    if t is None:
        return None
    return _ET.localize(dt.datetime.combine(d, t)).astimezone(pytz.UTC)


def fetch() -> pl.DataFrame:
    if not FRED_API_KEY:
        log.warning("fred.fetch skipped: FRED_API_KEY not set")
        return from_rows([])

    from fredapi import Fred  # imported lazily
    fred = Fred(api_key=FRED_API_KEY)
    now_utc = dt.datetime.now(dt.timezone.utc)
    rows: list[dict] = []

    for rid, name, slug, category, tier, t_et, comment in FRED_RELEASES:
        try:
            dates = fred.get_release_dates(
                rid, include_release_dates_with_no_data=False
            )
        except Exception as e:  # noqa: BLE001
            log.warning("fred release %s (%s) failed: %s", rid, name, e)
            continue

        url = f"https://fred.stlouisfed.org/release?rid={rid}"
        for d in dates:
            d = d if isinstance(d, date) else d.date()
            rows.append({
                "event_id":              f"{slug}_{d.isoformat()}",
                "event_name":            name,
                "event_category":        category,
                "release_date":          d,
                "release_time_et":       t_et,
                "release_timestamp_utc": _et_to_utc(d, t_et),
                "period":                _prior_month_period(d),
                "tier":                  tier,
                "source":                SOURCE,
                "source_url":            url,
                "scraped_at":            now_utc,
                "notes":                 comment,
            })

    return from_rows(rows)
