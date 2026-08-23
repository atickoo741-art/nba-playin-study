"""Loading of the whiteboard workbook and of the independent source files.

Two independent copies of the same games are available:

* the ``Regular games`` sheet of ``NBA_PlayIn_Whiteboard_Data.xlsx`` (the
  spreadsheet the study is built around), and
* ``data/external/nba_schedule_master.csv``, freshly retrieved from the
  sportsdataverse/hoopR-nba-data archive that the workbook cites.

The audit step compares them. Every later step uses the workbook copy, so the
study is reproducible from the workbook alone.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import config

_WORKBOOK_CACHE: dict[str, pd.DataFrame] = {}


def _sheet_raw(sheet: str) -> pd.DataFrame:
    if sheet not in _WORKBOOK_CACHE:
        _WORKBOOK_CACHE[sheet] = pd.read_excel(
            config.WORKBOOK, sheet_name=sheet, header=None, dtype=object,
            engine="openpyxl",
        )
    return _WORKBOOK_CACHE[sheet]


def load_table(sheet: str, header_row: int = 4, block: int = 0) -> pd.DataFrame:
    """Return one contiguous table from a workbook sheet.

    The sheets carry a title, a note and a blank line before the header row, and
    some of them hold several tables separated by blank rows. ``block`` selects
    which of those tables to return; ``header_row`` is the 0-based row index of
    the first table's header.
    """
    raw = _sheet_raw(sheet)
    blank = raw.isna().all(axis=1)
    start = header_row
    for _ in range(block):
        # Skip to the header of the next table: first blank row after the
        # current block, then the next non-blank row.
        i = start + 1
        while i < len(raw) and not blank.iloc[i]:
            i += 1
        while i < len(raw) and blank.iloc[i]:
            i += 1
        start = i
    end = start + 1
    while end < len(raw) and not blank.iloc[end]:
        end += 1
    header = [str(c).strip() for c in raw.iloc[start]]
    body = raw.iloc[start + 1:end].copy()
    body.columns = header
    body = body.loc[:, [c for c in body.columns if c != "nan"]]
    return body.reset_index(drop=True)


@dataclass
class Workbook:
    """Every workbook table the study uses, in tidy form."""

    games: pd.DataFrame          # 9,519 regular-season games, 2017-18..2024-25
    teams: pd.DataFrame          # 150 team-seasons with records and ratings
    training: pd.DataFrame       # pregame features published by the workbook
    postseason: pd.DataFrame     # actual play-in and playoff games
    model_fit: pd.DataFrame      # coefficients published by the workbook
    validation: pd.DataFrame     # validation published by the workbook
    matchups: pd.DataFrame
    playin_states: pd.DataFrame
    advancement: pd.DataFrame
    bracket_weights: pd.DataFrame
    reference_summary: pd.DataFrame
    reference_teams: pd.DataFrame
    reference_sensitivity: pd.DataFrame
    discrepancies: pd.DataFrame
    checks: pd.DataFrame


def _num(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def load_workbook() -> Workbook:
    games = load_table("Regular games")
    games = _num(games, ["Season end", "Home score", "Away score"])
    games["Game date"] = pd.to_datetime(games["Game date"]).dt.normalize()
    for c in ["Source neutral", "Model neutral"]:
        games[c] = games[c].astype(str).str.strip().str.lower().map(
            {"true": True, "false": False}
        )
    games["ESPN game ID"] = games["ESPN game ID"].astype(str)

    teams = load_table("Teams")
    teams = _num(teams, [
        "Season end", "Regular rank", "Wins", "Losses", "Game-log PF",
        "Game-log PA", "ESPN seed field", "Games", "Mean margin",
        "Schedule strength", "Computed SRS", "Standings PF", "Standings PA",
    ])

    training = load_table("Training data")
    training = _num(training, [
        "Season end", "Home SRS before", "Away SRS before", "SRS difference",
        "H", "Home won", "Home prior games", "Away prior games",
    ])
    training["Game date"] = pd.to_datetime(training["Game date"]).dt.normalize()
    training["ESPN game ID"] = training["ESPN game ID"].astype(str)

    postseason = load_table("Actual postseason")
    postseason = _num(postseason, ["Season end", "Home score", "Away score"])
    postseason["Game date"] = pd.to_datetime(postseason["Game date"]).dt.normalize()
    postseason["ESPN game ID"] = postseason["ESPN game ID"].astype(str)

    model_fit = _num(load_table("Model fit", block=0), [
        "Test season", "Prior seasons", "Training start", "Training end",
        "Training games", "beta", "h",
    ])
    validation = _num(load_table("Model fit", block=1), [
        "Test season", "Prior seasons", "Games", "Brier score", "Log loss",
        "Accuracy",
    ])

    matchups = _num(load_table("Matchups"), [
        "Season end", "A SRS", "B SRS", "P(A), A home", "P(A), A away",
        "P(A), neutral", "Series A, A hosts first", "Series A, B hosts first",
    ])
    playin_states = _num(load_table("Play-in states", block=0),
                         ["Season end", "State", "Probability"])
    advancement = _num(load_table("Advancement"), [
        "Season end", "Old: round 1 win", "Old: round 2 win",
        "Old: conference win", "Old: title", "New: round 1 win",
        "New: round 2 win", "New: conference win", "New: title",
    ])
    bracket_weights = _num(load_table("Bracket weights"), [
        "Bracket", "East weight", "West weight", "Joint weight",
        "P(title | bracket)", "Weighted contribution",
    ])

    ref_summary = _num(load_table("Reference results", block=0), [
        "Season end", "Prior seasons", "Old title P", "New title P",
        "Difference", "Old champion SRS", "New champion SRS",
        "Old field SRS sum", "New field SRS sum",
    ])
    ref_teams = _num(load_table("Reference results", block=2), [
        "Season end", "Regular rank", "SRS", "Old qualify P", "New qualify P",
        "Old title P", "New title P", "Title difference",
    ])
    ref_sens = _num(load_table("Reference results", block=4), [
        "Season end", "Prior seasons", "Old title P", "New title P",
        "Difference", "Old champion SRS", "New champion SRS",
        "Old field SRS sum", "New field SRS sum",
    ])

    notes = _sheet_raw("Data notes")
    checks = _table_from_notes(notes, "Season end", ["Regular games", "Teams"])
    disc = _table_from_notes(notes, "Season end", ["Team", "Game-log PF"])
    return Workbook(
        games=games, teams=teams, training=training, postseason=postseason,
        model_fit=model_fit, validation=validation, matchups=matchups,
        playin_states=playin_states, advancement=advancement,
        bracket_weights=bracket_weights, reference_summary=ref_summary,
        reference_teams=ref_teams, reference_sensitivity=ref_sens,
        discrepancies=disc, checks=checks,
    )


def _table_from_notes(raw: pd.DataFrame, first: str, must_have: list[str]) -> pd.DataFrame:
    """Pull one labelled table out of the free-form ``Data notes`` sheet."""
    blank = raw.isna().all(axis=1)
    for i in range(len(raw)):
        row = [str(c).strip() for c in raw.iloc[i]]
        if row and row[0] == first and all(m in row for m in must_have):
            end = i + 1
            while end < len(raw) and not blank.iloc[end]:
                end += 1
            body = raw.iloc[i + 1:end].copy()
            body.columns = row
            body = body.loc[:, [c for c in body.columns if c != "nan"]]
            return body.reset_index(drop=True)
    raise KeyError(f"table starting {first!r} with {must_have} not found")


def load_notes_code() -> str:
    """Return the processing-code appendix stored in the ``Data notes`` sheet."""
    raw = _sheet_raw("Data notes")
    lines = []
    for i in range(len(raw)):
        a, b = raw.iloc[i, 0], raw.iloc[i, 1]
        if isinstance(a, (int, float)) and not pd.isna(a) and isinstance(b, str):
            lines.append((int(a), b))
        elif isinstance(a, (int, float)) and not pd.isna(a) and (b is None or pd.isna(b)):
            lines.append((int(a), ""))
    return "\n".join(t for _, t in sorted(lines))


# --------------------------------------------------------------------------
# Independent sources
# --------------------------------------------------------------------------

def load_external_schedule() -> pd.DataFrame:
    """Load the hoopR schedule archive and apply the documented filters."""
    cols = [
        "game_id", "season", "season_type", "game_date", "neutral_site",
        "status_type_completed", "home_id", "away_id", "home_abbreviation",
        "away_abbreviation", "home_score", "away_score", "notes_headline",
        "venue_full_name",
    ]
    raw = pd.read_csv(config.SCHEDULE_CSV, low_memory=False, usecols=cols)
    raw["game_date"] = pd.to_datetime(raw["game_date"]).dt.normalize()
    return raw


def load_external_standings() -> pd.DataFrame:
    rows = []
    for year in config.STUDY_SEASONS:
        data = json.loads((config.DATA_EXTERNAL / f"standings{year}.json").read_text())
        for conf in data["children"]:
            for entry in conf["standings"]["entries"]:
                st = {r["name"]: r.get("value") for r in entry["stats"]}
                rows.append(dict(
                    season=year,
                    conf=conf["name"].split()[0],
                    team_id=int(entry["team"]["id"]),
                    team=entry["team"]["abbreviation"],
                    name=entry["team"]["displayName"],
                    wins=int(st["wins"]),
                    losses=int(st["losses"]),
                    points_for=int(st["pointsFor"]),
                    points_against=int(st["pointsAgainst"]),
                    espn_seed=int(st["playoffSeed"]),
                ))
    return pd.DataFrame(rows)


def team_index(teams: pd.DataFrame) -> dict[str, int]:
    """Stable 0..29 index for the 30 NBA teams, ordered alphabetically."""
    codes = sorted(teams["Team"].unique())
    assert len(codes) == 30, f"expected 30 teams, found {len(codes)}"
    return {t: i for i, t in enumerate(codes)}


def to_float(x) -> float:
    return float(np.asarray(x, dtype=float))
