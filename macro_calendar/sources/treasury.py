"""Treasury auctions (fiscaldata REST) + refunding (deterministic schedule).

The spec calls for scraping press releases for refunding announcements; we
compute them from the well-known quarterly cadence instead — the dates are
deterministic and avoiding a fragile HTML scrape is sturdier. A real refunding
press-release scrape would emit identical dates with possibly different times.
"""
from __future__ import annotations

import datetime as dt
import logging
from datetime import date, time
from typing import Any

import polars as pl
import pytz

from .._http import get
from ..config import (
    AUCTION_TIERS, AUCTION_TIME_ET, REFUNDING_DETAILS_TIME_ET,
    REFUNDING_FIN_EST_TIME_ET, TREASURY_AUCTIONS_URL, TREASURY_PRESS_URL,
)
from ..schema import from_rows

log = logging.getLogger(__name__)

SOURCE = "treasury_api"
_ET = pytz.timezone("America/New_York")

ALLOWED_TYPES = {"Note", "Bond"}
TENOR_MAP = {
    "2-Year":  "2-Year Note", "3-Year":  "3-Year Note", "5-Year":  "5-Year Note",
    "7-Year":  "7-Year Note", "10-Year": "10-Year Note",
    "20-Year": "20-Year Bond", "30-Year": "30-Year Bond",
}


def _et_to_utc(d: date, t: time | None) -> dt.datetime | None:
    if t is None:
        return None
    return _ET.localize(dt.datetime.combine(d, t)).astimezone(pytz.UTC)


def _parse_date(s: str | None) -> date | None:
    if not s: return None
    try: return date.fromisoformat(s)
    except ValueError: return None


def _fetch_auctions() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    page = 1
    while True:
        try:
            r = get(TREASURY_AUCTIONS_URL, **{"page[size]": 10000, "page[number]": page})
        except Exception as e:  # noqa: BLE001
            log.warning("treasury auctions page %d failed: %s", page, e)
            break
        payload = r.json()
        rows = payload.get("data", [])
        if not rows:
            break
        out.extend(rows)
        meta = payload.get("meta") or {}
        if page * 10000 >= int(meta.get("total-count", 0)):
            break
        page += 1
    log.info("treasury: fetched %d auction rows across %d pages", len(out), page)
    return out


def _auction_events(rows: list[dict[str, Any]], now_utc: dt.datetime) -> list[dict]:
    events: list[dict] = []
    for r in rows:
        sec_type = r.get("security_type")
        if sec_type not in ALLOWED_TYPES:
            continue
        if r.get("inflation_index_security") == "Yes":
            continue  # TIPS — separate market, optional in spec
        # Reopenings tag `security_term` with remaining maturity (e.g.
        # "9-Year 11-Month"). `original_security_term` preserves the issue
        # tenor, which is what gets the calendar event.
        term_raw = (r.get("original_security_term") or r.get("security_term") or "").strip()
        key = next((k for k in TENOR_MAP if term_raw.lower().startswith(k.lower())), None)
        if key is None:
            continue
        ad = _parse_date(r.get("auction_date"))
        if ad is None:
            continue
        label = TENOR_MAP[key]
        tier = AUCTION_TIERS.get(label, 4)
        cusip = r.get("cusip") or "noCUSIP"
        if cusip == "null":
            cusip = "noCUSIP"
        notes_bits = []
        for f in ("high_yield", "bid_to_cover_ratio", "offering_amt", "issue_date"):
            v = r.get(f)
            if v not in (None, "", "null"):
                notes_bits.append(f"{f}={v}")
        events.append({
            "event_id":              f"auction_{label.replace(' ', '_')}_{ad.isoformat()}_{cusip}",
            "event_name":            f"{label} Auction",
            "event_category":        "auction",
            "release_date":          ad,
            "release_time_et":       AUCTION_TIME_ET,
            "release_timestamp_utc": _et_to_utc(ad, AUCTION_TIME_ET),
            "period":                None,
            "tier":                  tier,
            "source":                SOURCE,
            "source_url":            TREASURY_AUCTIONS_URL,
            "scraped_at":            now_utc,
            "notes":                 "; ".join(notes_bits) or None,
        })
    return events


def _first_weekday_of_month(year: int, month: int, weekday: int) -> date:
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return date.fromordinal(first.toordinal() + offset)


def _refunding_events(now_utc: dt.datetime) -> list[dict]:
    """Quarterly refunding: Feb/May/Aug/Nov first week. Monday financing
    estimate at 15:00 ET; Wednesday refunding details at 8:30 ET."""
    events: list[dict] = []
    year_start = 2000
    year_end   = dt.date.today().year + 2
    for y in range(year_start, year_end + 1):
        for m in (2, 5, 8, 11):
            mon = _first_weekday_of_month(y, m, weekday=0)
            wed = _first_weekday_of_month(y, m, weekday=2)
            # If Monday's first occurrence is *after* Wednesday's in the month
            # (i.e. month starts on Tue/Wed/Thu/Fri), the financing-estimate
            # Monday is the one in the *first business week*, which is the
            # following Monday. Use the standard convention: first Monday of
            # the month, even if it's the 2nd–7th.
            events.append({
                "event_id":              f"refunding_fin_est_{mon.isoformat()}",
                "event_name":            "Treasury Refunding: Financing Estimate",
                "event_category":        "treasury_admin",
                "release_date":          mon,
                "release_time_et":       REFUNDING_FIN_EST_TIME_ET,
                "release_timestamp_utc": _et_to_utc(mon, REFUNDING_FIN_EST_TIME_ET),
                "period":                f"{y} Q{(m + 1) // 3}",
                "tier":                  3,
                "source":                SOURCE,
                "source_url":            TREASURY_PRESS_URL,
                "scraped_at":            now_utc,
                "notes":                 "computed: first Monday of refunding month",
            })
            events.append({
                "event_id":              f"refunding_details_{wed.isoformat()}",
                "event_name":            "Treasury Refunding: Details",
                "event_category":        "treasury_admin",
                "release_date":          wed,
                "release_time_et":       REFUNDING_DETAILS_TIME_ET,
                "release_timestamp_utc": _et_to_utc(wed, REFUNDING_DETAILS_TIME_ET),
                "period":                f"{y} Q{(m + 1) // 3}",
                "tier":                  3,
                "source":                SOURCE,
                "source_url":            TREASURY_PRESS_URL,
                "scraped_at":            now_utc,
                "notes":                 "computed: first Wednesday of refunding month",
            })
    return events


def fetch() -> pl.DataFrame:
    now_utc = dt.datetime.now(dt.timezone.utc)
    rows = _auction_events(_fetch_auctions(), now_utc)
    rows.extend(_refunding_events(now_utc))
    return from_rows(rows)
