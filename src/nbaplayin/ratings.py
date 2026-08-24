"""Step 2a: team ratings.

Two rating definitions are produced for every season:

* **SRS** (the baseline). Solve, for every team i,

      R_i = mbar_i + (1 / n_i) * sum_{j in O_i} R_j,        sum_i R_i = 0,

  where mbar_i is team i's average scoring margin, n_i its number of games and
  O_i the list of its opponents with one entry per game played. In matrix form
  this is (diag(N) - C) R = total margins with a sum-to-zero constraint, where
  C[i, j] counts the games between i and j.

* **Bradley-Terry** (the alternative specification). Ratings on a log-odds
  scale fitted to wins and losses only, ignoring margins, with a ridge penalty
  so that early-season fits stay finite.

Both come in two flavours: full-season ratings frozen before the postseason,
and pregame ratings that use only games played on earlier dates.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit

from . import config

RIDGE = 1.0  # ridge penalty on Bradley-Terry ratings, in squared log-odds


def solve_srs(counts: np.ndarray, totals: np.ndarray) -> np.ndarray:
    """Solve the SRS system with the sum-to-zero constraint.

    ``counts[i, j]`` is the number of games between i and j and ``totals[i]``
    team i's total scoring margin. The augmented least-squares solve returns the
    minimum-norm solution when the schedule graph is not yet connected, which
    only happens in the first days of a season.
    """
    n = len(totals)
    laplacian = np.diag(counts.sum(axis=1)) - counts
    aug = np.zeros((n + 1, n + 1))
    aug[:n, :n] = laplacian
    aug[n, :n] = 1.0
    aug[:n, n] = 1.0
    sol = np.linalg.lstsq(aug, np.r_[totals, 0.0], rcond=None)[0][:n]
    return sol - sol.mean()


def fit_bradley_terry(counts_home: np.ndarray, wins_home: np.ndarray,
                      n_teams: int = 30) -> tuple[np.ndarray, float]:
    """Fit ridge Bradley-Terry ratings plus a home-court term.

    ``counts_home[i, j]`` is the number of games team i hosted against j and
    ``wins_home[i, j]`` how many of those the host won. Ratings are centred.
    """
    idx = np.argwhere(counts_home > 0)
    if len(idx) == 0:
        return np.zeros(n_teams), 0.0
    i, j = idx[:, 0], idx[:, 1]
    n = counts_home[i, j]
    w = wins_home[i, j]

    def objective(params):
        r = params[:n_teams]
        h = params[n_teams]
        z = r[i] - r[j] + h
        p = expit(z)
        nll = (n * np.logaddexp(0, z)).sum() - (w * z).sum() + RIDGE * (r @ r)
        grad_r = np.zeros(n_teams)
        resid = n * p - w
        np.add.at(grad_r, i, resid)
        np.add.at(grad_r, j, -resid)
        grad_r += 2 * RIDGE * r
        grad_h = resid.sum()
        return nll, np.r_[grad_r, grad_h]

    start = np.zeros(n_teams + 1)
    fit = minimize(objective, start, jac=True, method="L-BFGS-B",
                   options={"ftol": 1e-14, "gtol": 1e-10, "maxiter": 2000})
    r = fit.x[:n_teams]
    return r - r.mean(), float(fit.x[n_teams])


def season_tables(games: pd.DataFrame, index: dict[str, int]) -> dict:
    """Full-season ratings, frozen before the postseason, for every season.

    Returns a dict keyed by season end year, each holding the SRS vector, the
    Bradley-Terry vector and the raw schedule matrices.
    """
    out = {}
    n = len(index)
    for season, g in games.groupby("Season end"):
        counts = np.zeros((n, n))
        totals = np.zeros(n)
        ch = np.zeros((n, n))
        wh = np.zeros((n, n))
        for r in g.itertuples():
            i, j = index[r.Home], index[r.Away]
            margin = r._6 - r._7
            counts[i, j] += 1
            counts[j, i] += 1
            totals[i] += margin
            totals[j] -= margin
            ch[i, j] += 1
            wh[i, j] += 1 if margin > 0 else 0
        srs = solve_srs(counts, totals)
        bt, bt_home = fit_bradley_terry(ch, wh, n)
        out[int(season)] = dict(srs=srs, bt=bt, bt_home=bt_home,
                                counts=counts, totals=totals, games=len(g))
    return out


def pregame_features(games: pd.DataFrame, index: dict[str, int],
                     min_prior: int = config.MIN_PRIOR_GAMES,
                     with_bt: bool = True) -> pd.DataFrame:
    """Build one feature row per game from information available before it.

    Ratings are recomputed once per game date from games on strictly earlier
    dates, so no result from the day of the game or later can enter its own
    prediction. A row is kept only when both teams already have ``min_prior``
    games in that season.
    """
    n = len(index)
    rows = []
    for season, g in games.groupby("Season end"):
        counts = np.zeros((n, n))
        totals = np.zeros(n)
        ch = np.zeros((n, n))
        wh = np.zeros((n, n))
        for date, day in g.groupby("Game date", sort=True):
            played = counts.sum(axis=1)
            srs_before = solve_srs(counts, totals)
            if with_bt and played.max() >= min_prior:
                bt_before, _ = fit_bradley_terry(ch, wh, n)
            else:
                bt_before = np.zeros(n)
            for r in day.itertuples():
                i, j = index[r.Home], index[r.Away]
                if played[i] >= min_prior and played[j] >= min_prior:
                    rows.append(dict(
                        season=int(season), game_id=str(r._2), date=date,
                        home=r.Home, away=r.Away,
                        home_srs_before=srs_before[i],
                        away_srs_before=srs_before[j],
                        srs_difference=srs_before[i] - srs_before[j],
                        home_bt_before=bt_before[i], away_bt_before=bt_before[j],
                        bt_difference=bt_before[i] - bt_before[j],
                        H=0 if r._9 else 1,
                        home_win=int(r._6 > r._7),
                        home_prior_games=int(played[i]),
                        away_prior_games=int(played[j])))
            for r in day.itertuples():
                i, j = index[r.Home], index[r.Away]
                margin = r._6 - r._7
                counts[i, j] += 1
                counts[j, i] += 1
                totals[i] += margin
                totals[j] -= margin
                ch[i, j] += 1
                wh[i, j] += 1 if margin > 0 else 0
    return pd.DataFrame(rows)
