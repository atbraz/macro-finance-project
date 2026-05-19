"""Static configuration: release-time table, URLs, tiers."""
from __future__ import annotations

import os
from datetime import time
from pathlib import Path

# ---- API keys (env only) -------------------------------------------------
FRED_API_KEY = os.environ.get("FRED_API_KEY")

# ---- HTTP client ---------------------------------------------------------
USER_AGENT = "macro-calendar/0.1 (research; contact via repo)"
HTTP_TIMEOUT_S = 10.0
HTTP_MAX_ATTEMPTS = 5

# ---- Cache ---------------------------------------------------------------
CACHE_DIR = Path(os.environ.get("MACRO_CALENDAR_CACHE", Path.home() / ".macro_calendar"))
CACHE_DB = CACHE_DIR / "cache.duckdb"

# ---- FRED release IDs ----------------------------------------------------
# (release_id, event_name, slug, category, tier, release_time_et, source_comment)
FRED_RELEASES: list[tuple[int, str, str, str, int, time | None, str]] = [
    (10,  "CPI",                          "cpi",            "inflation", 1, time(8, 30),  "BLS, 8:30 ET, ~mid-month"),
    (46,  "PPI",                          "ppi",            "inflation", 2, time(8, 30),  "BLS, 8:30 ET"),
    (50,  "Employment Situation (NFP)",   "nfp",            "labor",     1, time(8, 30),  "BLS, 8:30 ET, first Friday"),
    (192, "JOLTS",                        "jolts",          "labor",     2, time(10, 0),  "BLS, 10:00 ET"),
    (87,  "Employment Cost Index",        "eci",            "labor",     2, time(8, 30),  "BLS, 8:30 ET"),
    (180, "Initial Jobless Claims",       "iclaims",        "labor",     2, time(8, 30),  "DOL, 8:30 ET, weekly Thu"),
    (21,  "PCE (Personal Income/Outlays)","pce",            "inflation", 1, time(8, 30),  "BEA, 8:30 ET"),
    (53,  "Gross Domestic Product",       "gdp",            "growth",    2, time(8, 30),  "BEA, 8:30 ET"),
    (130, "Advance Retail Sales",         "retail_sales",   "growth",    2, time(8, 30),  "Census, 8:30 ET"),
    (175, "ADP National Employment",      "adp",            "labor",     2, time(8, 15),  "ADP, 8:15 ET"),
    (235, "Industrial Production",        "indprod",        "growth",    3, time(9, 15),  "Fed, 9:15 ET"),
    (99,  "New Residential Construction", "housing_starts", "growth",    3, time(8, 30),  "Census, 8:30 ET"),
]

# ---- Fed Board URLs ------------------------------------------------------
FOMC_CURRENT_URL    = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
FOMC_HISTORICAL_FMT = "https://www.federalreserve.gov/monetarypolicy/fomchistorical{year}.htm"
JACKSON_HOLE_URL    = "https://www.kansascityfed.org/research/jackson-hole-economic-symposium/"
FOMC_FIRST_YEAR     = 1994

# ---- Treasury ------------------------------------------------------------
TREASURY_AUCTIONS_URL = (
    "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/"
    "v1/accounting/od/auctions_query"
)
TREASURY_PRESS_URL = "https://home.treasury.gov/news/press-releases"
AUCTION_TIME_ET = time(13, 0)
REFUNDING_FIN_EST_TIME_ET     = time(15, 0)   # Monday 3pm ET
REFUNDING_DETAILS_TIME_ET     = time(8, 30)   # Wednesday 8:30am ET

AUCTION_TIERS = {
    "10-Year Note": 3, "30-Year Bond": 3,
    "2-Year Note": 4, "3-Year Note": 4, "5-Year Note": 4,
    "7-Year Note": 4, "20-Year Bond": 4,
}

# ---- ECB -----------------------------------------------------------------
ECB_ICS_URL = "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html"
ECB_DECISION_TIME_CET     = time(14, 15)
ECB_PRESSCONF_TIME_CET    = time(14, 45)

# ---- Deterministic windows -----------------------------------------------
DET_START = "2000-01-01"
DET_FORWARD_YEARS = 2
