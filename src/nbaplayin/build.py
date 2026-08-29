"""Assemble fitted season models from the workbook data.

This is the glue between the audited game table, the ratings, the fitted
coefficients and the tournament engine.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import config, data_load, model as model_mod, ratings as ratings_mod
from .tournament import SeasonModel


@dataclass
class Study:
    workbook: data_load.Workbook
    index: dict[str, int]
    codes: list[str]
    features: pd.DataFrame
    season_tables: dict
    records: pd.DataFrame          # one row per team-season
    head_to_head: dict             # (season, a, b) -> (wins_a, wins_b)
    vs_other_conf: dict            # (season, team) -> win percentage


def load_study(with_bt: bool = True) -> Study:
    wb = data_load.load_workbook()
    index = data_load.team_index(wb.teams)
    codes = [None] * len(index)
    for code, i in index.items():
        codes[i] = code
    tables = ratings_mod.season_tables(wb.games, index)
    features = ratings_mod.pregame_features(wb.games, index, with_bt=with_bt)
    records = wb.teams.rename(columns={
        "Season end": "season", "Conference": "conference",
        "Regular rank": "rank", "Team": "team", "Wins": "wins",
        "Losses": "losses", "Games": "games", "Computed SRS": "srs"})
    h2h, vs_conf = _cross_conference_records(wb, index)
    return Study(workbook=wb, index=index, codes=codes, features=features,
                 season_tables=tables, records=records, head_to_head=h2h,
                 vs_other_conf=vs_conf)


def _cross_conference_records(wb: data_load.Workbook, index: dict[str, int]):
    """Head-to-head and versus-other-conference records, for Finals hosting."""
    conf = {(int(r._1), r.Team): r.Conference for r in wb.teams.itertuples()}
    h2h: dict = {}
    tally: dict = {}
    for r in wb.games.itertuples():
        season = int(r._1)
        if season not in config.STUDY_SEASONS:
            continue
        ch, ca = conf.get((season, r.Home)), conf.get((season, r.Away))
        if ch is None or ca is None or ch == ca:
            continue
        home_won = r._6 > r._7
        a, b = index[r.Home], index[r.Away]
        wa, wb_ = h2h.get((season, a, b), (0, 0))
        h2h[(season, a, b)] = (wa + int(home_won), wb_ + int(not home_won))
        wb2, wa2 = h2h.get((season, b, a), (0, 0))
        h2h[(season, b, a)] = (wb2 + int(not home_won), wa2 + int(home_won))
        for team, won in ((a, home_won), (b, not home_won)):
            w, n = tally.get((season, team), (0, 0))
            tally[(season, team)] = (w + int(won), n + 1)
    vs_conf = {k: w / n for k, (w, n) in tally.items()}
    return h2h, vs_conf


def season_model(study: Study, season: int, fit, spec: str = "srs",
                 finals_tiebreak: str = "nba") -> SeasonModel:
    rec = study.records[study.records.season == season]
    idx = study.index
    r = (study.season_tables[season]["srs"] if spec == "srs"
         else study.season_tables[season]["bt"])
    h2h = {(idx[a], idx[b]): v for (s, a, b), v in
           [((s, study.codes[a], study.codes[b]), v)
            for (s, a, b), v in study.head_to_head.items() if s == season]}
    voc = {t: v for (s, t), v in study.vs_other_conf.items() if s == season}
    return SeasonModel(
        season=season, codes=list(study.codes), ratings=np.asarray(r, float),
        beta=fit.beta, h=fit.h,
        conference={idx[x.team]: x.conference for x in rec.itertuples()},
        rank={idx[x.team]: int(x.rank) for x in rec.itertuples()},
        wins={idx[x.team]: int(x.wins) for x in rec.itertuples()},
        games_played={idx[x.team]: int(x.games) for x in rec.itertuples()},
        head_to_head=h2h, vs_other_conf=voc, finals_tiebreak=finals_tiebreak)
