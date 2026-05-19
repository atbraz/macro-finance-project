"""ECB Governing Council monetary policy meetings.

The spec calls for parsing the ECB iCalendar feed. The advertised endpoints
all return the generic ECB HTML shell (the calendar is JS-rendered, the
underlying data path is opaque). So the strategy is:

  1. Try the spec's ICS URL (and a few variants). If any returns a valid
     iCalendar payload, parse it with `icalendar` and emit events.
  2. Otherwise fall back to a hardcoded table of GC monetary policy meetings
     publicly announced by the ECB through 2026. Mark `notes='hardcoded'`.

When the ECB exposes a stable ICS endpoint, drop the fallback.
"""
from __future__ import annotations

import datetime as dt
import logging
from datetime import date, time

import polars as pl
import pytz
from icalendar import Calendar

from .._http import get
from ..config import ECB_DECISION_TIME_CET, ECB_ICS_URL, ECB_PRESSCONF_TIME_CET
from ..schema import from_rows

log = logging.getLogger(__name__)

SOURCE = "ecb_ics"
_CET = pytz.timezone("Europe/Berlin")  # ECB's local time

_ICS_CANDIDATES = [
    ECB_ICS_URL,
    "https://www.ecb.europa.eu/press/calendars/mgcgc/shared/calendar.ics",
    "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.ics",
]

# Published GC monetary policy decision dates (ECB.europa.eu).
# Update annually when the ECB publishes the following year.
_FALLBACK_DATES: list[date] = [
    # 2022
    date(2022, 2, 3), date(2022, 3, 10), date(2022, 4, 14), date(2022, 6, 9),
    date(2022, 7, 21), date(2022, 9, 8), date(2022, 10, 27), date(2022, 12, 15),
    # 2023
    date(2023, 2, 2), date(2023, 3, 16), date(2023, 5, 4), date(2023, 6, 15),
    date(2023, 7, 27), date(2023, 9, 14), date(2023, 10, 26), date(2023, 12, 14),
    # 2024
    date(2024, 1, 25), date(2024, 3, 7), date(2024, 4, 11), date(2024, 6, 6),
    date(2024, 7, 18), date(2024, 9, 12), date(2024, 10, 17), date(2024, 12, 12),
    # 2025
    date(2025, 1, 30), date(2025, 3, 6), date(2025, 4, 17), date(2025, 6, 5),
    date(2025, 7, 24), date(2025, 9, 11), date(2025, 10, 30), date(2025, 12, 18),
    # 2026
    date(2026, 1, 29), date(2026, 3, 5), date(2026, 4, 30), date(2026, 6, 4),
    date(2026, 7, 23), date(2026, 9, 10), date(2026, 10, 29), date(2026, 12, 17),
]


def _cet_to_utc(d: date, t: time) -> dt.datetime:
    return _CET.localize(dt.datetime.combine(d, t)).astimezone(pytz.UTC)


def _try_ics() -> list[date] | None:
    """Try ICS candidates in order. Return list of decision dates or None."""
    for url in _ICS_CANDIDATES:
        try:
            r = get(url)
        except Exception as e:  # noqa: BLE001
            log.info("ecb: ICS candidate %s failed: %s", url, e)
            continue
        body = r.text
        if "BEGIN:VCALENDAR" not in body:
            log.info("ecb: %s did not return iCalendar payload", url)
            continue
        cal = Calendar.from_ical(body)
        dates: list[date] = []
        for ev in cal.walk("VEVENT"):
            summary = str(ev.get("SUMMARY", "")).lower()
            if "monetary policy" not in summary:
                continue
            dtstart = ev.get("DTSTART").dt
            d = dtstart.date() if isinstance(dtstart, dt.datetime) else dtstart
            dates.append(d)
        log.info("ecb: parsed %d MP events from %s", len(dates), url)
        return sorted(set(dates))
    return None


def fetch() -> pl.DataFrame:
    now_utc = dt.datetime.now(dt.timezone.utc)
    dates = _try_ics()
    used_fallback = False
    if not dates:
        log.warning("ecb: ICS unavailable, using hardcoded date table")
        dates = _FALLBACK_DATES
        used_fallback = True

    rows: list[dict] = []
    for d in dates:
        rows.append({
            "event_id":              f"ecb_{d.isoformat()}",
            "event_name":            "ECB GC Monetary Policy Decision",
            "event_category":        "central_bank_foreign",
            "release_date":          d,
            "release_time_et":       None,                 # CET event; ET not strictly defined
            "release_timestamp_utc": _cet_to_utc(d, ECB_DECISION_TIME_CET),
            "period":                f"{d.year}-{d.month:02d}",
            "tier":                  4,
            "source":                SOURCE,
            "source_url":            ECB_ICS_URL,
            "scraped_at":            now_utc,
            "notes":                 "hardcoded fallback" if used_fallback else None,
        })
        rows.append({
            "event_id":              f"ecb_press_{d.isoformat()}",
            "event_name":            "ECB Press Conference",
            "event_category":        "central_bank_foreign",
            "release_date":          d,
            "release_time_et":       None,
            "release_timestamp_utc": _cet_to_utc(d, ECB_PRESSCONF_TIME_CET),
            "period":                f"{d.year}-{d.month:02d}",
            "tier":                  4,
            "source":                SOURCE,
            "source_url":            ECB_ICS_URL,
            "scraped_at":            now_utc,
            "notes":                 ("hardcoded fallback" if used_fallback else None),
        })
    return from_rows(rows)
