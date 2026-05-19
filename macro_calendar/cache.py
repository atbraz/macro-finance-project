"""DuckDB-backed cache. One `events` table + an `events_pulls` audit table."""
from __future__ import annotations

import datetime as dt
import logging

import duckdb
import polars as pl

from .config import CACHE_DB, CACHE_DIR
from .schema import COLUMNS, coerce, empty_frame

log = logging.getLogger(__name__)

_DDL_EVENTS = """
CREATE TABLE IF NOT EXISTS events (
    event_id              VARCHAR PRIMARY KEY,
    event_name            VARCHAR,
    event_category        VARCHAR,
    release_date          DATE,
    release_time_et       TIME,
    release_timestamp_utc TIMESTAMPTZ,
    period                VARCHAR,
    tier                  TINYINT,
    source                VARCHAR,
    source_url            VARCHAR,
    scraped_at            TIMESTAMPTZ,
    notes                 VARCHAR
);
"""

_DDL_PULLS = """
CREATE TABLE IF NOT EXISTS events_pulls (
    source                  VARCHAR PRIMARY KEY,
    last_successful_pull_utc TIMESTAMPTZ,
    row_count               INTEGER
);
"""


def _conn() -> duckdb.DuckDBPyConnection:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    c = duckdb.connect(str(CACHE_DB))
    c.execute(_DDL_EVENTS)
    c.execute(_DDL_PULLS)
    return c


def upsert(rows: pl.DataFrame, source: str) -> int:
    """Upsert rows by event_id; record pull in events_pulls. Returns rows written."""
    if rows.is_empty():
        log.info("cache.upsert: 0 rows for source=%s", source)
        return 0
    rows = coerce(rows)
    cols = ", ".join(COLUMNS)
    updates = ", ".join(f"{c}=excluded.{c}" for c in COLUMNS if c != "event_id")
    sql = (
        f"INSERT INTO events ({cols}) "
        f"SELECT {cols} FROM rows "
        f"ON CONFLICT (event_id) DO UPDATE SET {updates}"
    )
    with _conn() as c:
        c.register("rows", rows)
        c.execute(sql)
        c.unregister("rows")
        c.execute(
            "INSERT INTO events_pulls VALUES (?, ?, ?) "
            "ON CONFLICT (source) DO UPDATE SET "
            "  last_successful_pull_utc = excluded.last_successful_pull_utc, "
            "  row_count = excluded.row_count",
            [source, dt.datetime.now(dt.timezone.utc), rows.height],
        )
    return rows.height


def load() -> pl.DataFrame:
    with _conn() as c:
        try:
            return c.execute(f"SELECT {', '.join(COLUMNS)} FROM events").pl()
        except duckdb.CatalogException:
            return empty_frame()


def last_pull_age_hours(source: str | None = None) -> float | None:
    """Hours since the oldest (or specified) successful pull, or None if never."""
    with _conn() as c:
        q = "SELECT MIN(last_successful_pull_utc) FROM events_pulls"
        params: list = []
        if source is not None:
            q += " WHERE source = ?"
            params.append(source)
        row = c.execute(q, params).fetchone()
    if not row or row[0] is None:
        return None
    delta = dt.datetime.now(dt.timezone.utc) - row[0]
    return delta.total_seconds() / 3600.0


def pulls_table() -> pl.DataFrame:
    with _conn() as c:
        return c.execute("SELECT * FROM events_pulls").pl()
