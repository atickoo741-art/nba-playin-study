"""Step 6a: held-out predictive validation.

Nothing here touches the tournament comparison. The question is only whether
the game model predicts games it has never seen better than a naive rule.

Three test sets per study season:

* regular season, using pregame ratings built from earlier dates only;
* the play-in games, single games with a known host;
* the playoffs, using full-season ratings frozen before the postseason.

The comparison model is the home-win rate on the training window's non-neutral
games, which ignores team strength entirely.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config, model as model_mod


def postseason_frame(study, spec: str = "srs") -> pd.DataFrame:
    """Actual play-in and playoff games with frozen full-season rating gaps."""
    ps = study.workbook.postseason.rename(columns={
        "Season end": "season", "Stage": "stage", "Home": "home",
        "Away": "away", "Home score": "home_score", "Away score": "away_score"})
    idx = study.index
    key = "srs" if spec == "srs" else "bt"
    diff, H, y = [], [], []
    for r in ps.itertuples():
        ratings = study.season_tables[int(r.season)][key]
        diff.append(ratings[idx[r.home]] - ratings[idx[r.away]])
        H.append(1)          # every postseason game in the study is hosted
        y.append(int(r.home_score > r.away_score))
    out = ps.copy()
    out["difference"] = diff
    out["H"] = H
    out["home_win"] = y
    return out


def evaluate(study, specs=("srs", "bt"), windows=config.WINDOWS) -> pd.DataFrame:
    rows = []
    post = {spec: postseason_frame(study, spec) for spec in specs}
    for spec in specs:
        col = "srs_difference" if spec == "srs" else "bt_difference"
        for season in config.STUDY_SEASONS:
            for window in windows:
                fit = model_mod.fit_window(study.features, season, window, spec)
                train = study.features[study.features.season.between(
                    season - window, season - 1)]
                base_rate = model_mod.home_rate_baseline(train)
                tests = {
                    "Regular season (pregame ratings)":
                        study.features[study.features.season == season]
                        .rename(columns={col: "difference"}),
                    "Play-in games (frozen ratings)":
                        post[spec][(post[spec].season == season)
                                   & (post[spec].stage == "Play-in")],
                    "Playoffs (frozen ratings)":
                        post[spec][(post[spec].season == season)
                                   & (post[spec].stage == "Playoffs")],
                }
                for label, test in tests.items():
                    if len(test) == 0:
                        continue
                    d = test["difference"].to_numpy(float)
                    H = test["H"].to_numpy(float)
                    y = test["home_win"].to_numpy(int)
                    p = model_mod.predict(fit, d, H)
                    # Naive model: training home-win rate where there is a host,
                    # 0.5 at a neutral venue.
                    pb = np.where(H == 0, 0.5, base_rate)
                    rows.append(dict(
                        season=season, spec=spec, window=window,
                        test_set=label, games=len(test),
                        beta=fit.beta, h=fit.h, train_games=fit.n_train,
                        brier=model_mod.brier(p, y),
                        log_loss=model_mod.log_loss(p, y),
                        accuracy=model_mod.accuracy(p, y),
                        brier_baseline=model_mod.brier(pb, y),
                        log_loss_baseline=model_mod.log_loss(pb, y),
                        accuracy_baseline=model_mod.accuracy(pb, y),
                        baseline_home_rate=base_rate))
    return pd.DataFrame(rows)


def pooled_calibration(study, spec: str = "srs",
                       window: int = config.BASELINE_WINDOW) -> pd.DataFrame:
    """Calibration over all five study seasons pooled, held out each season."""
    ps, ys = [], []
    for season in config.STUDY_SEASONS:
        fit = model_mod.fit_window(study.features, season, window, spec)
        test = study.features[study.features.season == season]
        col = "srs_difference" if spec == "srs" else "bt_difference"
        ps.append(model_mod.predict(fit, test[col].to_numpy(float),
                                    test["H"].to_numpy(float)))
        ys.append(test["home_win"].to_numpy(int))
    p = np.concatenate(ps)
    y = np.concatenate(ys)
    tbl = model_mod.calibration_table(p, y)
    tbl.insert(0, "spec", spec)
    return tbl


def coefficient_table(study, specs=("srs", "bt"),
                      windows=config.WINDOWS) -> pd.DataFrame:
    rows = []
    for spec in specs:
        for season in config.STUDY_SEASONS:
            for window in windows:
                fit = model_mod.fit_window(study.features, season, window, spec)
                rows.append(dict(
                    season=season, spec=spec, window=window,
                    train_first=fit.seasons[0], train_last=fit.seasons[1],
                    train_games=fit.n_train, beta=fit.beta, h=fit.h,
                    beta_se=fit.std_errors[0], h_se=fit.std_errors[1],
                    converged=fit.converged,
                    role=("prespecified baseline"
                          if window == config.BASELINE_WINDOW
                          else "sensitivity window")))
    return pd.DataFrame(rows)
