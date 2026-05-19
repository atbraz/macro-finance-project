"""Orchestrator: runs sources sequentially, caches, exposes filter helpers."""
from __future__ import annotations

import datetime as dt
import logging
from typing import Callable

import polars as pl

from . import cache
from .sources import deterministic, ecb, fed_board, fred, treasury

log = logging.getLogger(__name__)

SOURCES: dict[str, Callable[[], pl.DataFrame]] = {
    "deterministic": deterministic.fetch,
    "fred":          fred.fetch,
    "treasury":      treasury.fetch,
    "fed_board":     fed_board.fetch,
    "ecb":           ecb.fetch,
}

CACHE_MAX_AGE_H = 24


def build_calendar(
    refresh: bool = False,
    sources: list[str] | None = None,
) -> pl.DataFrame:
    """Run sources, upsert into cache, return the unified frame.

    Args:
        refresh: if False and cache < 24h old, skip all source pulls.
        sources: subset of source names; None means all.
    """
    selected = sources or list(SOURCES)

    age = cache.last_pull_age_hours()
    fresh = age is not None and age < CACHE_MAX_AGE_H
    if not refresh and fresh and not sources:
        log.info("pipeline: cache fresh (%.1fh), serving from cache", age)
        return cache.load().sort("release_timestamp_utc", nulls_last=True)

    for name in selected:
        if name not in SOURCES:
            log.warning("pipeline: unknown source %s, skipping", name)
            continue
        try:
            log.info("pipeline: fetching %s", name)
            df = SOURCES[name]()
            n = cache.upsert(df, source=name)
            log.info("pipeline: %s -> %d rows", name, n)
        except Exception as e:  # noqa: BLE001
            log.exception("pipeline: source %s failed: %s", name, e)

    return cache.load().sort("release_timestamp_utc", nulls_last=True)


# ---- filter helpers -----------------------------------------------------
def filter_window(df: pl.DataFrame, start: dt.date, end: dt.date) -> pl.DataFrame:
    return df.filter(
        (pl.col("release_date") >= start) & (pl.col("release_date") <= end)
    )


def tier(df: pl.DataFrame, max_tier: int) -> pl.DataFrame:
    return df.filter(pl.col("tier") <= max_tier)


def around(
    df: pl.DataFrame,
    anchor_date: dt.date,
    days_before: int = 2,
    days_after: int = 2,
) -> pl.DataFrame:
    lo = anchor_date - dt.timedelta(days=days_before)
    hi = anchor_date + dt.timedelta(days=days_after)
    return filter_window(df, lo, hi)
