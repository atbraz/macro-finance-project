"""FOMC meetings + minutes from federalreserve.gov, plus Jackson Hole.

Two HTML layouts to parse:
  - Current calendar page covers ~2021–2027 with `.fomc-meeting` rows.
  - Historical pages (one per year, 1994–2020) put each meeting in its own
    panel with a heading like "January 26-27 Meeting - 2010".
"""
from __future__ import annotations

import datetime as dt
import logging
import re
from datetime import date, time, timedelta
from typing import Iterable

import polars as pl
import pytz
from bs4 import BeautifulSoup

from .._http import get
from ..config import (
    FOMC_CURRENT_URL, FOMC_FIRST_YEAR, FOMC_HISTORICAL_FMT, JACKSON_HOLE_URL,
)
from ..schema import from_rows

log = logging.getLogger(__name__)

SOURCE = "fed_board"
_ET = pytz.timezone("America/New_York")
SEP_MONTHS = {3, 6, 9, 12}

_MONTH_FULL = ["January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December"]
_MONTH = {m: i for i, m in enumerate(_MONTH_FULL, start=1)}
# Abbreviations the Fed uses in cross-month labels ("Jan/Feb", "Apr/May", "Oct/Nov")
_MONTH.update({m[:3]: i for i, m in enumerate(_MONTH_FULL, start=1)})

_HIST_HEADING_RE = re.compile(
    r"(?P<month>[A-Z][a-z]+)\s+(?P<d1>\d+)(?:\s*[-/]\s*(?P<d2>\d+))?\s*\*?\s*Meeting\s*-\s*(?P<year>\d{4})"
)
_MINUTES_RELEASED_RE = re.compile(r"Released\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})")


def _et_to_utc(d: date, t: time | None) -> dt.datetime | None:
    if t is None:
        return None
    return _ET.localize(dt.datetime.combine(d, t)).astimezone(pytz.UTC)


def _build_events(meetings: Iterable[dict], now_utc: dt.datetime) -> list[dict]:
    """Each meeting dict: {year, month, start_day, end_day, has_sep, minutes_date|None, url}."""
    rows: list[dict] = []
    for m in meetings:
        try:
            decision_date = date(m["year"], m["month"], m["end_day"])
        except (ValueError, KeyError):
            continue
        has_sep = m.get("has_sep") or decision_date.month in SEP_MONTHS
        post_2011 = decision_date.year >= 2011
        decision_notes = []
        if has_sep: decision_notes.append("SEP")
        if post_2011: decision_notes.append("press conference 14:30 ET")
        rows.append({
            "event_id":              f"fomc_{decision_date.isoformat()}",
            "event_name":            "FOMC Decision",
            "event_category":        "fed",
            "release_date":          decision_date,
            "release_time_et":       time(14, 0),
            "release_timestamp_utc": _et_to_utc(decision_date, time(14, 0)),
            "period":                None,
            "tier":                  1,
            "source":                SOURCE,
            "source_url":            m.get("url") or FOMC_CURRENT_URL,
            "scraped_at":            now_utc,
            "notes":                 "; ".join(decision_notes) or None,
        })
        mdate = m.get("minutes_date") or (decision_date + timedelta(days=21))
        rows.append({
            "event_id":              f"fomc_minutes_{mdate.isoformat()}",
            "event_name":            "FOMC Minutes",
            "event_category":        "fed",
            "release_date":          mdate,
            "release_time_et":       time(14, 0),
            "release_timestamp_utc": _et_to_utc(mdate, time(14, 0)),
            "period":                f"FOMC {decision_date.isoformat()}",
            "tier":                  1,
            "source":                SOURCE,
            "source_url":            m.get("url") or FOMC_CURRENT_URL,
            "scraped_at":            now_utc,
            "notes":                 "computed +3 weeks" if not m.get("minutes_date") else None,
        })
    return rows


def _parse_current(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    meetings: list[dict] = []
    for panel in soup.select("div.panel"):
        heading = panel.select_one(".panel-heading")
        if not heading: continue
        m = re.search(r"(\d{4})\s+FOMC\s+Meetings?", heading.get_text())
        if not m: continue
        year = int(m.group(1))
        for row in panel.select(".row.fomc-meeting"):
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["div"], recursive=False)]
            cells = [c for c in cells if c]
            if len(cells) < 2: continue
            month_name = cells[0].strip().split("/")[0].strip()  # handles "April/May"
            if month_name not in _MONTH: continue
            date_str = cells[1].strip()
            # Skip notation votes / procedural items — no rate decision.
            if "notation" in date_str.lower():
                continue
            has_sep = "*" in date_str
            nums = re.findall(r"\d+", date_str)
            if not nums: continue
            start_day = int(nums[0])
            end_day = int(nums[-1])
            # Cross-month meetings (rare, e.g. "April/May" "28-1"): keep end month
            end_month = month_name
            if "/" in cells[0]:
                end_month = cells[0].split("/")[1].strip()
            minutes_text = " ".join(cells[2:])
            mm = _MINUTES_RELEASED_RE.search(minutes_text)
            minutes_date = None
            if mm:
                try:
                    minutes_date = dt.datetime.strptime(mm.group(1), "%B %d, %Y").date()
                except ValueError:
                    pass
            meetings.append({
                "year": year, "month": _MONTH[end_month],
                "start_day": start_day, "end_day": end_day,
                "has_sep": has_sep, "minutes_date": minutes_date,
                "url": FOMC_CURRENT_URL,
            })
    return meetings


def _parse_historical(html: str, year: int, url: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    meetings: list[dict] = []
    for heading in soup.select(".panel-heading"):
        m = _HIST_HEADING_RE.search(heading.get_text(" ", strip=True))
        if not m: continue
        try:
            mo = _MONTH[m.group("month")]
        except KeyError:
            continue
        d1 = int(m.group("d1"))
        d2 = int(m.group("d2")) if m.group("d2") else d1
        has_sep = "*" in heading.get_text()
        meetings.append({
            "year": year, "month": mo,
            "start_day": d1, "end_day": d2,
            "has_sep": has_sep, "minutes_date": None,
            "url": url,
        })
    return meetings


def _jackson_hole(now_utc: dt.datetime) -> list[dict]:
    """Last Friday of August at 10:00 ET. Approximate; Powell's opening speech."""
    rows: list[dict] = []
    for y in range(1994, dt.date.today().year + 2):
        last = date(y + (8 == 12), (8 % 12) + 1, 1) - timedelta(days=1)
        back = (last.weekday() - 4) % 7
        d = last - timedelta(days=back)
        rows.append({
            "event_id":              f"jackson_hole_{d.isoformat()}",
            "event_name":            "Jackson Hole Opening Speech",
            "event_category":        "fed",
            "release_date":          d,
            "release_time_et":       time(10, 0),
            "release_timestamp_utc": _et_to_utc(d, time(10, 0)),
            "period":                f"{y}",
            "tier":                  1,
            "source":                SOURCE,
            "source_url":            JACKSON_HOLE_URL,
            "scraped_at":            now_utc,
            "notes":                 "computed: last Friday of August",
        })
    return rows


def fetch() -> pl.DataFrame:
    now_utc = dt.datetime.now(dt.timezone.utc)
    all_meetings: list[dict] = []

    try:
        r = get(FOMC_CURRENT_URL)
        all_meetings.extend(_parse_current(r.text))
    except Exception as e:  # noqa: BLE001
        log.warning("fed_board: current calendar failed: %s", e)

    seen_years = {m["year"] for m in all_meetings}
    for y in range(FOMC_FIRST_YEAR, dt.date.today().year + 1):
        if y in seen_years:
            continue
        url = FOMC_HISTORICAL_FMT.format(year=y)
        try:
            r = get(url)
        except Exception as e:  # noqa: BLE001
            log.info("fed_board: historical %d skipped (%s)", y, e)
            continue
        all_meetings.extend(_parse_historical(r.text, y, url))

    rows = _build_events(all_meetings, now_utc)
    rows.extend(_jackson_hole(now_utc))
    return from_rows(rows)
