"""Step 2b: the logistic game-probability model.

    P(A beats B) = 1 / (1 + exp(-(beta * (R_A - R_B) + h * H)))

with H = +1 when A is at home, -1 when A is away and 0 at a neutral venue. The
coefficients are fitted by unpenalised maximum likelihood on completed games
from earlier seasons only, with beta constrained to be non-negative and no
separate intercept (a neutral game between equally rated teams is a coin flip
by construction).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit

from . import config


@dataclass
class Fit:
    beta: float
    h: float
    n_train: int
    seasons: tuple[int, int]
    spec: str
    converged: bool
    message: str
    std_errors: tuple[float, float]


def fit_logistic(diff: np.ndarray, H: np.ndarray, y: np.ndarray) -> tuple[float, float, bool, str, tuple[float, float]]:
    X = np.column_stack([diff, H]).astype(float)
    y = y.astype(float)

    def objective(b):
        z = X @ b
        nll = np.logaddexp(0.0, z).sum() - y @ z
        grad = X.T @ (expit(z) - y)
        return nll, grad

    res = minimize(objective, np.array([0.12, 0.2]), jac=True, method="L-BFGS-B",
                   bounds=[(0.0, None), (None, None)],
                   options={"ftol": 1e-12, "gtol": 1e-8})
    beta, h = map(float, res.x)
    z = X @ res.x
    w = expit(z) * (1 - expit(z))
    info = X.T @ (X * w[:, None])
    try:
        se = np.sqrt(np.diag(np.linalg.inv(info)))
    except np.linalg.LinAlgError:
        se = np.array([np.nan, np.nan])
    return beta, h, bool(res.success), str(res.message), (float(se[0]), float(se[1]))


def fit_window(features: pd.DataFrame, test_season: int, window: int,
               spec: str = "srs") -> Fit:
    """Fit on the ``window`` completed seasons before ``test_season``."""
    col = "srs_difference" if spec == "srs" else "bt_difference"
    train = features[features.season.between(test_season - window, test_season - 1)]
    beta, h, ok, msg, se = fit_logistic(train[col].to_numpy(),
                                        train["H"].to_numpy(),
                                        train["home_win"].to_numpy())
    return Fit(beta=beta, h=h, n_train=len(train),
               seasons=(test_season - window, test_season - 1), spec=spec,
               converged=ok, message=msg, std_errors=se)


def predict(fit: Fit, diff: np.ndarray, H: np.ndarray) -> np.ndarray:
    return expit(fit.beta * np.asarray(diff, float) + fit.h * np.asarray(H, float))


def brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((np.asarray(p) - np.asarray(y)) ** 2))


def log_loss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(np.asarray(p, float), 1e-12, 1 - 1e-12)
    y = np.asarray(y, float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def accuracy(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((np.asarray(p) >= 0.5) == np.asarray(y).astype(bool)))


def calibration_table(p: np.ndarray, y: np.ndarray, edges=None) -> pd.DataFrame:
    """Observed versus predicted home-win rate in fixed probability bins."""
    if edges is None:
        edges = np.array([0.0, 0.35, 0.45, 0.5, 0.55, 0.65, 0.75, 1.0])
    p = np.asarray(p, float)
    y = np.asarray(y, float)
    bins = np.clip(np.digitize(p, edges) - 1, 0, len(edges) - 2)
    rows = []
    for b in range(len(edges) - 1):
        m = bins == b
        if not m.any():
            continue
        rows.append(dict(bin_low=edges[b], bin_high=edges[b + 1], games=int(m.sum()),
                         mean_predicted=float(p[m].mean()),
                         observed=float(y[m].mean()),
                         standard_error=float(np.sqrt(
                             max(y[m].mean() * (1 - y[m].mean()), 1e-12) / m.sum()))))
    return pd.DataFrame(rows)


def home_rate_baseline(train: pd.DataFrame) -> float:
    """Home-win rate on non-neutral training games: the naive comparison model."""
    sub = train[train["H"] == 1]
    return float(sub["home_win"].mean())
