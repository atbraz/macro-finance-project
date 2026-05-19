"""Canonical schema every source emits rows in."""
from __future__ import annotations

import polars as pl

CATEGORIES = {
    "fed", "inflation", "labor", "growth", "survey",
    "auction", "central_bank_foreign", "treasury_admin",
}

SCHEMA = {
    "event_id":              pl.Utf8(),
    "event_name":            pl.Utf8(),
    "event_category":        pl.Utf8(),
    "release_date":          pl.Date(),
    "release_time_et":       pl.Time(),
    "release_timestamp_utc": pl.Datetime("us", "UTC"),
    "period":                pl.Utf8(),
    "tier":                  pl.Int8(),
    "source":                pl.Utf8(),
    "source_url":            pl.Utf8(),
    "scraped_at":            pl.Datetime("us", "UTC"),
    "notes":                 pl.Utf8(),
}

COLUMNS = list(SCHEMA.keys())


def empty_frame() -> pl.DataFrame:
    return pl.DataFrame(schema=SCHEMA)


def coerce(df: pl.DataFrame) -> pl.DataFrame:
    """Force the input frame to canonical schema and column order. Missing
    columns are filled with nulls; extras are dropped."""
    missing = [c for c in COLUMNS if c not in df.columns]
    df = df.with_columns([pl.lit(None).alias(c) for c in missing])
    return df.select(COLUMNS).cast(SCHEMA)  # type: ignore[arg-type]


def from_rows(rows: list[dict]) -> pl.DataFrame:
    """Build a canonical frame from a list of row dicts, bypassing Polars'
    type-inference (which fails when an early row has None where later ones
    have strings)."""
    if not rows:
        return empty_frame()
    return pl.from_dicts(rows, schema=SCHEMA)
