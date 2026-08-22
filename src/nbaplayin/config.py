"""Central configuration and paths for the NBA play-in study.

Everything that another module might want to tune lives here so that a reader
can see every analysis choice in one place.
"""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]

DATA_RAW = ROOT / "data" / "raw"
DATA_EXTERNAL = ROOT / "data" / "external"
DATA_PROCESSED = ROOT / "data" / "processed"
OUT_TABLES = ROOT / "outputs" / "tables"
OUT_FIGURES = ROOT / "outputs" / "figures"
REPORTS = ROOT / "reports"
LOGS = ROOT / "logs"

WORKBOOK = DATA_RAW / "NBA_PlayIn_Whiteboard_Data.xlsx"
SCHEDULE_CSV = DATA_EXTERNAL / "nba_schedule_master.csv"

# "Season end" labels: 2021 means the 2020-21 season.
STUDY_SEASONS = [2021, 2022, 2023, 2024, 2025]
# Earliest season retained in the game table (used only to build training windows).
FIRST_SEASON = 2018

# Training-window lengths, in completed prior seasons. 3 is the prespecified
# baseline; 1 and 2 are sensitivity checks only.
BASELINE_WINDOW = 3
WINDOWS = [1, 2, 3]

# A training game is used only when both teams already have this many games
# in the same season, so that pregame ratings are not built on a handful of games.
MIN_PRIOR_GAMES = 20

# Monte Carlo settings.
MC_REPLICATES = 500_000
MC_SEED = 20250921
MC_CHUNK = 20_000

# Venue pattern for a best-of-seven, from the point of view of the series host
# (the team that hosts game 1). True means the host is at home.
SERIES_HOME_PATTERN = [True, True, False, False, True, False, True]

# First-round pairings in a fixed eight-team bracket, by seed.
BRACKET_ORDER = [1, 8, 4, 5, 2, 7, 3, 6]

CONFERENCES = ["Eastern", "Western"]


def ensure_dirs() -> None:
    for p in [DATA_PROCESSED, OUT_TABLES, OUT_FIGURES, REPORTS, LOGS]:
        p.mkdir(parents=True, exist_ok=True)
