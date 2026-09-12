"""Ratings reproduce their defining equations and the workbook's values."""
import numpy as np
import pytest

from nbaplayin import ratings


def test_srs_solves_its_own_system(study):
    for season, tab in study.season_tables.items():
        counts, totals, r = tab["counts"], tab["totals"], tab["srs"]
        lhs = (np.diag(counts.sum(axis=1)) - counts) @ r
        assert np.max(np.abs(lhs - totals)) < 1e-7
        assert abs(r.sum()) < 1e-8


def test_srs_matches_the_workbook(study):
    for r in study.workbook.teams.itertuples():
        mine = study.season_tables[int(r._1)]["srs"][study.index[r.Team]]
        assert mine == pytest.approx(r._14, abs=1e-9)


def test_srs_equals_margin_plus_schedule_strength(study):
    """R_i = mean margin + mean opponent rating, by construction."""
    tab = study.season_tables[2025]
    counts, r = tab["counts"], tab["srs"]
    n = counts.sum(axis=1)
    mean_margin = tab["totals"] / n
    sos = (counts @ r) / n
    assert np.max(np.abs(r - (mean_margin + sos))) < 1e-8


def test_features_match_the_workbook(study):
    wb = study.workbook.training.copy()
    wb["ESPN game ID"] = wb["ESPN game ID"].astype(str)
    mine = study.features.copy()
    mine["game_id"] = mine["game_id"].astype(str)
    merged = mine.merge(wb, left_on="game_id", right_on="ESPN game ID")
    assert len(merged) == len(wb) == len(mine)
    assert np.max(np.abs(merged.srs_difference - merged["SRS difference"])) < 1e-9
    assert (merged.home_win == merged["Home won"]).all()


def test_no_future_information_in_features(study):
    """Every feature row's prior-game count uses strictly earlier dates only."""
    games = study.workbook.games
    sample = study.features.sample(300, random_state=0)
    for r in sample.itertuples():
        for team, stated in ((r.home, r.home_prior_games),
                             (r.away, r.away_prior_games)):
            played = games[(games["Season end"] == r.season)
                           & ((games.Home == team) | (games.Away == team))
                           & (games["Game date"] < r.date)]
            assert len(played) == stated


def test_minimum_prior_games_enforced(study):
    assert study.features.home_prior_games.min() >= 20
    assert study.features.away_prior_games.min() >= 20


def test_bradley_terry_is_centred(study):
    for season, tab in study.season_tables.items():
        assert abs(tab["bt"].sum()) < 1e-6
