"""Step 6b: sensitivity of the format comparison to the study's choices.

Each function returns the same shape of answer - the change in the strongest
team's title probability, old format versus play-in - under one changed
assumption, so the variants can be stacked next to the baseline.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd

from . import build, config, model as model_mod, ratings as ratings_mod, tournament

BASELINE = dict(spec="srs", window=config.BASELINE_WINDOW, finals="nba")


def _row(label: str, variant: str, season: int, res, model, target: int,
         target_label: str) -> dict:
    return dict(
        analysis=label, variant=variant, season=season,
        target_team=model.codes[target], target_rule=target_label,
        old=res.title_old[target], playin=res.title_new[target],
        difference=res.title_new[target] - res.title_old[target],
        expected_champion_old=res.expected_champion_rating[0],
        expected_champion_playin=res.expected_champion_rating[1],
        field_sum_old=res.expected_field_rating[0],
        field_sum_playin=res.expected_field_rating[1])


def exact_results(study, spec="srs", window=config.BASELINE_WINDOW,
                  finals="nba", ratings_override=None, features=None):
    """Solve every study season under one configuration."""
    out = {}
    feats = study.features if features is None else features
    for season in config.STUDY_SEASONS:
        fit = model_mod.fit_window(feats, season, window, spec)
        m = build.season_model(study, season, fit, spec=spec,
                               finals_tiebreak=finals)
        if ratings_override is not None:
            m = tournament.SeasonModel(
                season=m.season, codes=m.codes,
                ratings=np.asarray(ratings_override[season], float),
                beta=m.beta, h=m.h, conference=m.conference, rank=m.rank,
                wins=m.wins, games_played=m.games_played,
                head_to_head=m.head_to_head, vs_other_conf=m.vs_other_conf,
                finals_tiebreak=finals)
        out[season] = (m, tournament.solve_season(m), fit)
    return out


def window_and_spec(study) -> pd.DataFrame:
    """Training-window and rating-specification sensitivity."""
    rows = []
    baseline_strongest = {}
    for season, (m, res, _) in exact_results(study).items():
        baseline_strongest[season] = m.codes[res.strongest]
    for spec in ("srs", "bt"):
        for window in config.WINDOWS:
            for season, (m, res, fit) in exact_results(
                    study, spec=spec, window=window).items():
                variant = (f"{'SRS' if spec == 'srs' else 'Bradley-Terry'} ratings, "
                           f"{window}-season training window")
                rows.append(_row("training window and rating specification",
                                 variant, season, res, m, res.strongest,
                                 "this model's strongest team"))
                rows[-1]["beta"] = fit.beta
                rows[-1]["h"] = fit.h
                if spec != "srs":
                    # Also follow the team the baseline SRS model calls strongest.
                    tgt = m.codes.index(baseline_strongest[season])
                    rows.append(_row("training window and rating specification",
                                     variant, season, res, m, tgt,
                                     "baseline SRS strongest team"))
                    rows[-1]["beta"] = fit.beta
                    rows[-1]["h"] = fit.h
    return pd.DataFrame(rows)


def finals_hosting(study) -> pd.DataFrame:
    """Finals home court: published rule, pilot 50/50, and both forced extremes."""
    labels = {
        "nba": "NBA rule (record, then head-to-head, then opposite conference)",
        "fifty_fifty": "workbook pilot assumption: ties averaged 50/50",
        "east": "every tie given to the Eastern team",
        "west": "every tie given to the Western team",
    }
    rows = []
    for rule, label in labels.items():
        for season, (m, res, _) in exact_results(study, finals=rule).items():
            rows.append(_row("Finals hosting", label, season, res, m,
                             res.strongest, "baseline SRS strongest team"))
    return pd.DataFrame(rows)


def standings_margin_variant(study) -> pd.DataFrame:
    """Re-rate the season using the disputed standings totals instead.

    Twelve team-season scoring totals in the ESPN standings feed differ from the
    summed game scores by 1-3 points. The study keeps the game scores, which a
    third source confirms. This variant instead forces each team's total margin
    to the standings figure, which is the largest effect those 12 rows could
    have, and re-solves the ratings.
    """
    tallies = pd.read_csv(config.DATA_PROCESSED / "team_season_tallies.csv")
    override = {}
    for season in config.STUDY_SEASONS:
        tab = study.season_tables[season]
        totals = tab["totals"].copy()
        sub = tallies[tallies.season == season]
        for r in sub.itertuples():
            i = study.index[r.team]
            gap = (r.points_for - r.points_against) - (r.pf - r.pa)
            totals[i] += gap
        override[season] = ratings_mod.solve_srs(tab["counts"], totals)
    rows = []
    for season, (m, res, _) in exact_results(
            study, ratings_override=override).items():
        rows.append(_row("data discrepancies", "ratings forced to the ESPN "
                         "standings scoring totals", season, res, m,
                         res.strongest, "strongest under this variant"))
    return pd.DataFrame(rows)


def date_defect_variant(study) -> pd.DataFrame:
    """Move the one mis-dated archive game to its true date and refit."""
    games = study.workbook.games.copy()
    mask = games["ESPN game ID"] == "401161536"
    games.loc[mask, "Game date"] = pd.Timestamp("2020-02-29")
    feats = ratings_mod.pregame_features(games.sort_values(["Game date", "ESPN game ID"]),
                                         study.index, with_bt=False)
    rows = []
    for season, (m, res, _) in exact_results(study, features=feats).items():
        rows.append(_row("data discrepancies",
                         "archive date defect corrected (game 401161536 moved "
                         "to 2020-02-29)", season, res, m, res.strongest,
                         "baseline SRS strongest team"))
    return pd.DataFrame(rows)
